"""
SupervisorRuntime - M7.3. Owns the MECHANICS of driving one Supervisor
plan forward: calling the registered Supervisor's decide_next(),
validating the result uniformly (plan_validation.py), executing
RUN_AGENTS decisions via AgentRuntime (never anything below it), and
recording every decision - including validation rejections - as an
immutable SupervisionStep. This is the third application of the same
"pluggable decision contract + generic runtime that owns mechanics and
enforcement" shape already used twice in this codebase (Action / Step
Runner, Agent / AgentRuntime) - not a new pattern being introduced here.

Step-oriented by design, not a continuous loop. step() advances a plan by
exactly ONE decision and returns control to its caller - it does not
block waiting for anything. This is what makes a plan resumable across a
real-world wait (a human approval, a reply days later) without
SupervisorRuntime needing its own persistence or event system: a
Supervisor-invoking Workflow Action (future work, not built in M7.3) can
call step() once per Step Runner tick, persist the returned
SupervisionState into its own ActionInput.context (already-existing,
already-opaque JSONB working state - see app.workflow_engine.actions.base's
own docstring), and return ActionOutcome.PENDING when the decision is
WAIT - reusing the Workflow Engine's own already-built WorkflowInstance
WAITING/engine.wait_for_event machinery rather than this package
inventing a second, parallel one. run_to_suspension() below is a
convenience wrapper for the common fast path (a plan that never actually
needs to wait) - it is sugar over repeated step() calls, not a different
execution model.

Parallel execution: Supervisor only ever expresses INTENT (a RUN_AGENTS
decision naming N agent invocations with no declared ordering dependency
between them - see base.py's own docstring on AgentInvocationRequest).
This module owns HOW that intent is executed - today, a thread pool
(each AgentRuntime.run_with_metadata() call is I/O-bound, waiting on a
provider round-trip, so threads genuinely overlap wall-clock time even
under the GIL). Swapping this for asyncio or a distributed task queue
later touches only this module - no Supervisor implementation's
decide_next() would need to change, because none of them ever said HOW,
only THAT a batch has no ordering dependency.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app.ai_agents.base import AgentInput
from app.ai_agents.runtime import AgentRuntime
from app.supervisor.base import (
    AgentInvocationRequest,
    AgentStepResult,
    DecisionKind,
    SupervisionState,
    SupervisionStep,
    SupervisorDecision,
)
from app.supervisor.observability import ExecutionIdContext
from app.supervisor.plan_validation import validate_decision
from app.supervisor.registry import get_supervisor, resolve_default_version

_SUSPENDING_OR_TERMINAL_KINDS = frozenset(
    {DecisionKind.WAIT, DecisionKind.COMPLETE, DecisionKind.FAIL, DecisionKind.ABORT}
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SupervisorRuntime:
    @staticmethod
    def start_plan(plan_key: str, *, initial_context: dict) -> SupervisionState:
        """M7.4 convenience constructor for the common case - a caller
        (in practice, app.workflow_actions.supervisor_invocation_action's
        SupervisorInvocationAction) starting a BRAND NEW plan execution
        that doesn't want to hardcode which version to pin to. Resolves
        plan_key's current default version (app.supervisor.registry.
        resolve_default_version()) and mints a SupervisionState pinned to
        it.

        Deliberately NOT folded into SupervisionState.start() itself
        (base.py) - that classmethod stays a pure data constructor with
        no registry dependency, still directly usable (with an explicit
        plan_version) by anything that wants to pin to a SPECIFIC,
        non-default version on purpose (every test in
        tests/test_supervisor_e2e.py does exactly this, relying on
        plan_version's own default of 1). This method is the one place
        "start a plan the way a real caller would, using whatever's
        currently the default" lives - base.py = data + explicit-version
        construction; this module = mechanics + registry-backed
        convenience resolution, the same split every other pairing in
        this package already follows."""
        version = resolve_default_version(plan_key)
        return SupervisionState.start(plan_key=plan_key, initial_context=initial_context, plan_version=version)

    @staticmethod
    def step(state: SupervisionState, *, gateway=None) -> tuple[SupervisionState, SupervisorDecision]:
        """Advances `state` by exactly one decision. Never blocks on
        anything beyond the actual agent invocation(s) a RUN_AGENTS
        decision requires - never sleeps, never waits on an external
        event itself (a WAIT decision is recorded and returned to the
        caller to act on, not waited-on here).

        `gateway` is an opaque pass-through, forwarded unchanged to
        AgentRuntime.run_with_metadata()'s own `gateway` parameter - an
        optional injection point for tests only (see
        tests/test_supervisor_e2e.py's own FakeProviderClient-based
        tests). Deliberately left untyped here rather than annotated as
        AIGateway: this module has no legitimate reason to import
        app.ai_gateway at all (see package docstring) - the real type is
        AgentRuntime's own concern, one layer down, not this one's."""
        # M7.4: version-aware lookup - state.plan_version pins this
        # exact SupervisionState to whichever Supervisor implementation
        # produced its history so far, so a plan resumed after a newer
        # version has since become the default for NEW starts still
        # runs against the version it actually started on. See
        # app.supervisor.registry's own docstring for why this is a
        # code-level concern, not a database-governed one.
        supervisor = get_supervisor(state.plan_key, state.plan_version)
        started_at = _now()

        decision = supervisor.decide_next(state)

        validation = validate_decision(decision, state, supervisor)
        if not validation.is_valid:
            # Fail-closed: the ORIGINAL proposed decision's kind/reason
            # never gets acted on - it is replaced wholesale by an ABORT
            # carrying every validation error, so the rejection (and
            # what was rejected) is fully explainable from this one
            # recorded step alone.
            decision = SupervisorDecision.abort(
                reason=f"plan validation rejected a proposed '{decision.kind.value}' decision: {decision.reason}",
                error="; ".join(validation.errors),
            )

        agent_results: tuple[AgentStepResult, ...] = ()
        if decision.kind == DecisionKind.RUN_AGENTS:
            agent_results = SupervisorRuntime._execute_agents(decision.agent_invocations, state.execution_id, gateway=gateway)

        step = SupervisionStep(
            step_index=len(state.history),
            decision=decision,
            agent_results=agent_results,
            started_at=started_at,
            completed_at=_now(),
        )
        return state.with_step(step), decision

    @staticmethod
    def run_to_suspension(
        state: SupervisionState, *, gateway=None, max_iterations: int | None = None
    ) -> SupervisionState:
        """Convenience loop over step() - calls it repeatedly until a
        SUSPENDING_OR_TERMINAL decision (WAIT/COMPLETE/FAIL/ABORT) is
        reached, which is when this returns. The real, always-on safety
        net against a runaway plan is settings.SUPERVISOR_MAX_EXECUTION_DEPTH,
        enforced inside step() via plan_validation - once exceeded, the
        very next decision is forced to ABORT, which this loop treats as
        a normal suspending/terminal stop. `max_iterations` is an
        additional, optional, tighter local bound (e.g. useful in
        tests), not a substitute for the configured depth ceiling."""
        iterations = 0
        while True:
            state, decision = SupervisorRuntime.step(state, gateway=gateway)
            iterations += 1
            if decision.kind in _SUSPENDING_OR_TERMINAL_KINDS:
                return state
            if max_iterations is not None and iterations >= max_iterations:
                return state

    @staticmethod
    def _execute_agents(
        invocations: tuple[AgentInvocationRequest, ...], execution_id, *, gateway=None
    ) -> tuple[AgentStepResult, ...]:
        if len(invocations) == 1:
            return (SupervisorRuntime._invoke_one(invocations[0], execution_id, gateway=gateway),)

        # A shared `gateway` (when a test injects one) is safe to use
        # from multiple threads concurrently: AIGateway holds no mutable
        # instance state - complete() is a pure function of its
        # `request` argument (see app.ai_gateway.client's own docstring).
        results: list[AgentStepResult] = []
        with ThreadPoolExecutor(max_workers=len(invocations)) as pool:
            futures = [
                pool.submit(SupervisorRuntime._invoke_one, invocation, execution_id, gateway=gateway)
                for invocation in invocations
            ]
            for future in as_completed(futures):
                results.append(future.result())
        # Recorded in actual completion order, not request order - see
        # module docstring on why wall-clock order is not guaranteed
        # even though decision-level behavior is.
        return tuple(results)

    @staticmethod
    def _invoke_one(invocation: AgentInvocationRequest, execution_id, *, gateway=None) -> AgentStepResult:
        with ExecutionIdContext(str(execution_id)):
            agent_input = AgentInput(context=invocation.context, idempotency_key=invocation.idempotency_key)
            result = AgentRuntime.run_with_metadata(invocation.agent_key, agent_input, gateway=gateway)
        return AgentStepResult(
            agent_key=invocation.agent_key,
            output=result.output,
            provider_key=result.provider_key,
            model=result.model,
            usage=result.usage,
        )
