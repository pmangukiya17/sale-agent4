"""
SupervisionState (de)serialization - M7.4.

Exists specifically because SupervisorInvocationAction
(app/workflow_actions/supervisor_invocation_action.py) must persist a
suspended plan's state into a WorkflowInstance's own opaque JSONB
`context` (via ActionOutput.result, merged back by the Step Runner - see
app.workflow_engine.actions.base's own docstring) between Step Runner
ticks, and read it back on the next tick to resume exactly where it left
off. SupervisionState.base.py's own docstring names this exact scenario:
"designed to be fully JSON-serializable... SPECIFICALLY so that
persisting/resuming a suspended plan in a later milestone is additive."
This module is that later milestone - but scoped narrowly: it converts
SupervisionState to and from a plain JSON-safe dict, in-process, for one
Action's own bookkeeping. It is deliberately NOT a database model or an
Alembic migration - no new table exists for SupervisionState in M7.4; the
ONLY place a serialized SupervisionState lives is inside a
WorkflowInstance's own already-existing `context` column, riding along
with whatever else that step's context already carries. A real,
independently-queryable SupervisionState table (keyed by execution_id,
auditable outside any one WorkflowInstance's context - needed before old
Supervisor plan-code versions can ever be safely retired, per the M7.4
architecture review's own "Supervisor plan lifecycle" clarification)
remains explicitly future work.

Lives in app.supervisor (not app.workflow_actions) deliberately: only
this package should need to know SupervisionState's exact field-by-field
shape. app.workflow_actions calls state_to_dict()/state_from_dict() as
opaque conversions - the same encapsulation discipline every other layer
boundary in this codebase already follows (e.g. app.supervisor itself
never reaches into AgentRuntime's internals, only its public return
types).

TokenUsage is imported from app.ai_agents.base, exactly like base.py's
own AgentStepResult.usage field does, and for the identical reason (see
base.py's own docstring on this) - never from app.ai_gateway directly.
"""
import uuid
from datetime import datetime

from app.ai_agents.base import AgentOutcome, AgentOutput, TokenUsage
from app.supervisor.base import (
    SUPERVISION_STATE_SCHEMA_VERSION,
    AgentInvocationRequest,
    AgentStepResult,
    DecisionKind,
    ResumeTrigger,
    ResumeTriggerType,
    SupervisionState,
    SupervisionStep,
    SupervisorDecision,
)


def _usage_to_dict(usage: TokenUsage | None) -> dict | None:
    if usage is None:
        return None
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
        "cost_usd": usage.cost_usd,
    }


def _usage_from_dict(data: dict | None) -> TokenUsage | None:
    if data is None:
        return None
    return TokenUsage(
        prompt_tokens=data["prompt_tokens"],
        completion_tokens=data["completion_tokens"],
        total_tokens=data["total_tokens"],
        cost_usd=data.get("cost_usd"),
    )


def _agent_output_to_dict(output: AgentOutput) -> dict:
    return {"status": output.status.value, "result": output.result, "error": output.error}


def _agent_output_from_dict(data: dict) -> AgentOutput:
    return AgentOutput(status=AgentOutcome(data["status"]), result=data.get("result"), error=data.get("error"))


def _agent_result_to_dict(result: AgentStepResult) -> dict:
    return {
        "agent_key": result.agent_key,
        "output": _agent_output_to_dict(result.output),
        "provider_key": result.provider_key,
        "model": result.model,
        "usage": _usage_to_dict(result.usage),
    }


def _agent_result_from_dict(data: dict) -> AgentStepResult:
    return AgentStepResult(
        agent_key=data["agent_key"],
        output=_agent_output_from_dict(data["output"]),
        provider_key=data.get("provider_key"),
        model=data.get("model"),
        usage=_usage_from_dict(data.get("usage")),
    )


def _invocation_to_dict(invocation: AgentInvocationRequest) -> dict:
    return {
        "agent_key": invocation.agent_key,
        "context": invocation.context,
        "inputs_consumed": list(invocation.inputs_consumed),
        "idempotency_key": invocation.idempotency_key,
    }


def _invocation_from_dict(data: dict) -> AgentInvocationRequest:
    return AgentInvocationRequest(
        agent_key=data["agent_key"],
        context=data["context"],
        inputs_consumed=tuple(data.get("inputs_consumed", ())),
        idempotency_key=data.get("idempotency_key"),
    )


def _resume_trigger_to_dict(trigger: ResumeTrigger | None) -> dict | None:
    if trigger is None:
        return None
    return {"type": trigger.type.value, "payload": trigger.payload}


def _resume_trigger_from_dict(data: dict | None) -> ResumeTrigger | None:
    if data is None:
        return None
    return ResumeTrigger(type=ResumeTriggerType(data["type"]), payload=data.get("payload", {}))


def _decision_to_dict(decision: SupervisorDecision) -> dict:
    return {
        "kind": decision.kind.value,
        "reason": decision.reason,
        "agent_invocations": [_invocation_to_dict(invocation) for invocation in decision.agent_invocations],
        "skipped_agent_key": decision.skipped_agent_key,
        "resume_trigger": _resume_trigger_to_dict(decision.resume_trigger),
        "result": decision.result,
        "error": decision.error,
    }


def _decision_from_dict(data: dict) -> SupervisorDecision:
    return SupervisorDecision(
        kind=DecisionKind(data["kind"]),
        reason=data["reason"],
        agent_invocations=tuple(_invocation_from_dict(d) for d in data.get("agent_invocations", ())),
        skipped_agent_key=data.get("skipped_agent_key"),
        resume_trigger=_resume_trigger_from_dict(data.get("resume_trigger")),
        result=data.get("result"),
        error=data.get("error"),
    )


def _step_to_dict(step: SupervisionStep) -> dict:
    return {
        "step_index": step.step_index,
        "decision": _decision_to_dict(step.decision),
        "agent_results": [_agent_result_to_dict(result) for result in step.agent_results],
        "started_at": step.started_at.isoformat(),
        "completed_at": step.completed_at.isoformat(),
    }


def _step_from_dict(data: dict) -> SupervisionStep:
    return SupervisionStep(
        step_index=data["step_index"],
        decision=_decision_from_dict(data["decision"]),
        agent_results=tuple(_agent_result_from_dict(d) for d in data.get("agent_results", ())),
        started_at=datetime.fromisoformat(data["started_at"]),
        completed_at=datetime.fromisoformat(data["completed_at"]),
    )


def state_to_dict(state: SupervisionState) -> dict:
    """Converts one SupervisionState into a plain, JSON-safe dict - every
    value is a str/int/float/bool/None/list/dict, so this is always safe
    to store directly in a JSONB column or round-trip through
    `json.dumps`/`json.loads` unmodified. Round-trips exactly through
    state_from_dict() below - see
    tests/test_supervisor_invocation_action_e2e.py's own round-trip
    test."""
    return {
        "schema_version": state.schema_version,
        "plan_key": state.plan_key,
        "plan_version": state.plan_version,
        "execution_id": str(state.execution_id),
        "initial_context": state.initial_context,
        "history": [_step_to_dict(step) for step in state.history],
        "created_at": state.created_at.isoformat(),
        "updated_at": state.updated_at.isoformat(),
    }


def state_from_dict(data: dict) -> SupervisionState:
    """The inverse of state_to_dict() above. Deliberately does NOT
    attempt to handle any schema_version other than the current
    SUPERVISION_STATE_SCHEMA_VERSION - raises loudly and immediately
    rather than silently guessing at how an older/newer shape should be
    read. A real schema-migration path for a suspended plan that
    outlives a schema change is explicitly future work (see
    SupervisionState's own docstring on why schema_version exists as a
    reserved field in the first place)."""
    schema_version = data["schema_version"]
    if schema_version != SUPERVISION_STATE_SCHEMA_VERSION:
        raise ValueError(
            f"cannot deserialize a SupervisionState with schema_version={schema_version} - "
            f"this code only understands schema_version={SUPERVISION_STATE_SCHEMA_VERSION} "
            "(no schema-migration path exists yet - see this module's own docstring)"
        )
    return SupervisionState(
        schema_version=schema_version,
        plan_key=data["plan_key"],
        plan_version=data["plan_version"],
        execution_id=uuid.UUID(data["execution_id"]),
        initial_context=data["initial_context"],
        history=tuple(_step_from_dict(d) for d in data.get("history", ())),
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
    )
