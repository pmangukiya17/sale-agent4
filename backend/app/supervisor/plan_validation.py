"""
Plan Validation - M7.3. Uniform safety infrastructure, called by
SupervisorRuntime before acting on ANY decision from ANY Supervisor -
handwritten or LLM-driven alike. This is a deliberate design choice, not
the more obvious "only validate what a Planning Agent produced": a bug in
a hand-written Supervisor (a typo'd agent_key, an accidental unbounded
loop) is exactly as dangerous as a hallucinated one, and gating only the
LLM path would be inconsistent and weaker. This mirrors
app.workflow_engine.definitions.validate_step_graph() validating every
WorkflowDefinition activation regardless of who authored it - the gate
checks the shape and safety of the thing, not who produced it.

Fail-closed: if a RUN_AGENTS decision names N agent invocations and ANY
one of them is invalid, the WHOLE decision is rejected, not partially
executed - same "no partial activation" discipline
activate_definition()'s own hard validation gate already applies one
layer down.

What this checks, and what it deliberately does NOT try to check:
  - referenced agent exists: reuses AGENT_REGISTRY via
    is_agent_registered() - trivial, already-built infrastructure.
  - per-plan allowlist: Supervisor.allowed_agent_keys (see base.py) -
    the concrete guard against a plan naming an agent_key that exists
    SOMEWHERE in the registry but was never meant to be reachable from
    THIS plan.
  - decision shape: every kind's own required field is present (defense
    in depth on top of SupervisorDecision's classmethod constructors -
    nothing stops direct dataclass construction).
  - maximum execution depth: a hard ceiling on total steps
    (settings.SUPERVISOR_MAX_EXECUTION_DEPTH) - the practical guard
    against infinite loops. True infinite-loop detection is undecidable
    in general; a step-count ceiling is the same pragmatic tool
    app.workflow_engine's own per-step max_attempts already is for
    unbounded retries.
  - maximum plan cost: settings.SUPERVISOR_MAX_PLAN_COST_USD (soft,
    unset by default) - summed directly off SupervisionState.history,
    which already accumulates every agent invocation's real cost_usd for
    the life of one plan execution, so no new persistence is needed to
    enforce a real PER-PLAN ceiling (stronger than the Gateway's own
    single-request soft check one layer down).
  - Explicitly NOT checked here: recursion (a Supervisor's decisions
    only ever name agent_keys today, never other plan_keys - literal
    plan-to-plan recursion isn't expressible yet; the moment a future
    milestone allows a plan to invoke a sub-plan, this is exactly where
    that guard belongs). Also explicitly NOT checked: broader data/tenant
    access permissions (can this plan touch this company's data) - that
    is a distinct, larger authorization concern this module does not
    attempt to solve; this module is scoped to plan SHAPE and SAFETY
    only.
"""
from dataclasses import dataclass

from app.ai_agents.registry import is_agent_registered
from app.core.config import settings
from app.supervisor.base import DecisionKind, Supervisor, SupervisorDecision, SupervisionState


@dataclass(frozen=True)
class PlanValidationResult:
    errors: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _total_plan_cost_usd(state: SupervisionState) -> float:
    total = 0.0
    for step in state.history:
        for agent_result in step.agent_results:
            if agent_result.usage is not None and agent_result.usage.cost_usd is not None:
                total += agent_result.usage.cost_usd
    return total


def validate_decision(decision: SupervisorDecision, state: SupervisionState, supervisor: Supervisor) -> PlanValidationResult:
    errors: list[str] = []

    if len(state.history) >= settings.SUPERVISOR_MAX_EXECUTION_DEPTH:
        errors.append(
            f"max execution depth ({settings.SUPERVISOR_MAX_EXECUTION_DEPTH}) exceeded "
            f"({len(state.history)} steps already recorded)"
        )

    if decision.kind == DecisionKind.RUN_AGENTS:
        if not decision.agent_invocations:
            errors.append("RUN_AGENTS decision must include at least one agent invocation")
        for invocation in decision.agent_invocations:
            if not is_agent_registered(invocation.agent_key):
                errors.append(f"RUN_AGENTS references unknown agent_key '{invocation.agent_key}'")
            elif invocation.agent_key not in supervisor.allowed_agent_keys:
                errors.append(
                    f"agent_key '{invocation.agent_key}' is not in the allowlist declared by "
                    f"Supervisor plan '{supervisor.key}' (allowed: {sorted(supervisor.allowed_agent_keys)})"
                )

    elif decision.kind == DecisionKind.SKIP_AGENT:
        if not decision.skipped_agent_key:
            errors.append("SKIP_AGENT decision must name skipped_agent_key")

    elif decision.kind == DecisionKind.WAIT:
        if decision.resume_trigger is None:
            errors.append("WAIT decision must include a resume_trigger")

    elif decision.kind == DecisionKind.COMPLETE:
        if decision.result is None:
            errors.append("COMPLETE decision must include a result (use an empty dict if there is nothing to report)")

    elif decision.kind in (DecisionKind.FAIL, DecisionKind.ABORT):
        if not decision.error:
            errors.append(f"{decision.kind.value.upper()} decision must include an error")

    if settings.SUPERVISOR_MAX_PLAN_COST_USD is not None:
        total_cost = _total_plan_cost_usd(state)
        if total_cost >= settings.SUPERVISOR_MAX_PLAN_COST_USD:
            errors.append(
                f"max plan cost (${settings.SUPERVISOR_MAX_PLAN_COST_USD}) exceeded "
                f"(already spent ${total_cost:.6f})"
            )

    return PlanValidationResult(errors=tuple(errors))
