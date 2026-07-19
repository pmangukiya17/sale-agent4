"""
SupervisorInvocationAction - M7.4. The bridge between the Workflow Engine
and the Supervisor / Supervisor Runtime layer, exactly as designed in the
approved M7.4 architecture review: a new concrete Action, sibling to the
existing RecordExecutionAction, that reads a previously-persisted
SupervisionState back out of ActionInput.context (or starts a brand new
one on first invocation), drives it forward via
SupervisorRuntime.run_to_suspension(), and translates the terminal
decision into an ActionOutcome.

This is the ONLY file in app/workflow_actions/ that imports
app.supervisor - a deliberate, sanctioned NEW dependency edge introduced
by this milestone (see this package's own __init__.py docstring,
unchanged from M7.1/M7.2/M7.3 in every other respect: app/workflow_engine/
itself still has - and must always have - zero reference to
app.supervisor/app.ai_gateway/app.ai_agents/app.prompt_builder; only this
one domain-owned bridge Action does, the exact same "domain imports
engine, never the reverse" shape RecordExecutionAction already
established one file over). This module also NEVER imports
app.ai_gateway/app.ai_agents/app.prompt_builder directly - it only ever
reaches the AI stack THROUGH SupervisorRuntime, so a Supervisor-driven
plan can never be bypassed here either, satisfying the M7.3-established
"must never bypass AgentRuntime" constraint one layer further up.

How resumption works, end to end (mirrors WaitForEventAction's own
docstring shape one package over, but the actual mechanism deliberately
differs - see below for why):

  1. A step's action_config = {"plan_key": "<a plan_key registered in
     SUPERVISOR_REGISTRY with a default version set - see
     app.supervisor.registry.register_default_version()>"}. First
     invocation: input_data.context has no "_supervision_state" key yet,
     so SupervisorRuntime.start_plan() mints a brand new SupervisionState
     pinned to plan_key's current default version, seeded with the WHOLE
     of input_data.context as initial_context (the same "the instance's
     own accumulated context is exactly this step's input" convention
     every other Action already follows).
  2. SupervisorRuntime.run_to_suspension() drives the plan forward until
     it reaches WAIT / COMPLETE / FAIL / ABORT.
  3. COMPLETE -> ActionOutcome.SUCCESS. FAIL or ABORT -> ActionOutcome.
     FAILURE (the Workflow Engine's own ActionOutcome vocabulary has no
     distinct "aborted" state, so ABORT's own distinctness - real and
     meaningful one layer down, see app.supervisor.base's own docstring
     on why ABORT is kept separate from FAIL - is not visible at the
     WorkflowStepInvocation.status level; it remains fully visible in the
     serialized SupervisionState's own history for anyone who inspects
     it. A disclosed, deliberate information loss, not an oversight).
     Either way, the full serialized SupervisionState is written into
     result["_supervision_state"] regardless of outcome, so it stays
     inspectable in WorkflowStepInvocation.output / WorkflowInstance.context
     even after the step finishes - never discarded.
  4. WAIT -> ActionOutcome.PENDING. This is the SAME contract
     WaitForEventAction already uses (current_step_id left unchanged,
     WorkflowInstanceStatus.WAITING, and - the point of this correction -
     step_runner_worker.py's own PENDING branch never touches
     attempt_number/max_attempts at all, so a suspended plan consumes
     zero attempts, for as long as it stays suspended). This is a
     deliberate correction of this module's own FIRST implementation,
     which mapped WAIT to ActionOutcome.RETRY as an interim "time-based
     polling" workaround. That workaround was rejected on architectural
     review: WAIT means "suspend, remain durable, resume when the
     condition becomes true" - retrying repeatedly and eventually
     failing is a different, incompatible meaning, regardless of how the
     retries are framed. PENDING is the correct, already-existing engine
     primitive for "suspend, remain durable" - there is no reason a
     Supervisor-driven suspension should be modeled any differently from
     the engine's own built-in one.

     What PENDING does NOT yet provide, honestly disclosed rather than
     silently assumed: an automated path back to RUNNING.
     event_dispatcher_worker.py's own event-matching loop is hardcoded to
     only ever wake an instance WAITING on WAIT_FOR_EVENT_ACTION_KEY
     (`step_def.get("action_key") != WAIT_FOR_EVENT_ACTION_KEY:
     continue`), so an instance WAITING on THIS action_key has no
     automated waker today, for ANY ResumeTriggerType (TIME included -
     this module deliberately does NOT special-case TIME as "pollable"
     the way the rejected RETRY-based design did, since that would
     reintroduce exactly the same per-trigger-type asymmetry and
     attempt-consumption the correction is meant to remove; every
     ResumeTriggerType is treated uniformly as "durably suspended, no
     automated resume path yet"). This is architecturally correct, not a
     regression: this codebase already treats a WorkflowInstance WAITING
     on an event_type nothing currently emits as a legitimate, accepted
     state, not a bug - a Supervisor-driven WAIT deserves the identical
     treatment, not a lesser one dressed up as retry-driven progress.
     The long-term fix - an additive Event Dispatcher extension able to
     match a dynamically-supplied resume expectation (read from
     WorkflowInstance.context, since a Supervisor's trigger specifics are
     decided at runtime, not authoring time), instead of only a
     statically-declared step_def.action_config.event_type - remains
     proposed and explicitly deferred, exactly as it was before this
     correction. This module's job is limited to making SUSPENSION
     correct; building automated RESUMPTION is deliberately left to that
     future, still-unbuilt extension, per this milestone's own "avoid
     speculative infrastructure" constraint. Until it exists, a suspended
     plan is durable and fully inspectable (its serialized SupervisionState
     lives in WorkflowInstance.context - see result["_supervision_state"]
     below) but requires something outside this module (a future
     Dispatcher extension, or a manual/administrative resume) to flip its
     WorkflowInstance back to RUNNING.
"""
from app.supervisor.base import DecisionKind
from app.supervisor.runtime import SupervisorRuntime
from app.supervisor.serialization import state_from_dict, state_to_dict
from app.workflow_engine.actions.base import Action, ActionInput, ActionOutcome, ActionOutput
from app.workflow_engine.actions.registry import is_action_registered, register_action

SUPERVISOR_INVOCATION_ACTION_KEY = "workflow.supervisor_invocation"

# The one reserved context key this Action owns, mirroring
# WaitForEventAction's own single reserved key ("_woken_by_event") -
# opaque to the engine, meaningful only here and to state_from_dict()/
# state_to_dict() (app.supervisor.serialization).
_STATE_CONTEXT_KEY = "_supervision_state"

_TERMINAL_OUTCOME = {
    DecisionKind.COMPLETE: ActionOutcome.SUCCESS,
    DecisionKind.FAIL: ActionOutcome.FAILURE,
    DecisionKind.ABORT: ActionOutcome.FAILURE,
    # WAIT -> PENDING, not RETRY - see this module's own docstring for
    # the full reasoning behind this correction (a real suspension via
    # the engine's own existing PENDING/WAITING contract, consuming zero
    # attempts, matching WaitForEventAction's own precedent exactly).
    DecisionKind.WAIT: ActionOutcome.PENDING,
}


class SupervisorInvocationAction(Action):
    def __init__(self, *, gateway=None):
        """`gateway` is an opaque pass-through, forwarded unchanged to
        SupervisorRuntime.run_to_suspension()'s own `gateway` parameter -
        the same "optional injection point for tests only" shape
        AIGateway.__init__'s own `provider_lookup` and SupervisorRuntime's
        own `gateway` parameter already establish (see runtime.py's own
        docstring). The production instance registered at the bottom of
        this module uses the default (gateway=None, real provider
        resolution); tests construct their own instance directly with an
        injected fake gateway instead of going through the registry -
        see tests/test_supervisor_invocation_action_e2e.py. Deliberately
        untyped here for the same reason SupervisorRuntime itself leaves
        it untyped: this module has no legitimate reason to import
        app.ai_gateway either."""
        self._gateway = gateway

    def execute(self, input_data: ActionInput) -> ActionOutput:
        plan_key = input_data.action_config.get("plan_key")
        if not plan_key:
            return ActionOutput(
                status=ActionOutcome.FAILURE,
                error="SupervisorInvocationAction requires action_config={'plan_key': '<registered plan key>'}",
            )

        serialized_state = input_data.context.get(_STATE_CONTEXT_KEY)
        if serialized_state is None:
            state = SupervisorRuntime.start_plan(plan_key, initial_context=input_data.context)
        else:
            state = state_from_dict(serialized_state)

        final_state = SupervisorRuntime.run_to_suspension(state, gateway=self._gateway)

        if not final_state.history:
            # Defensive only - run_to_suspension() always calls step() at
            # least once, and step() always appends exactly one
            # SupervisionStep before returning (see runtime.py's own
            # docstring) - this branch should be unreachable.
            return ActionOutput(status=ActionOutcome.FAILURE, error="Supervisor plan produced no decision")

        decision = final_state.history[-1].decision
        outcome = _TERMINAL_OUTCOME.get(decision.kind, ActionOutcome.FAILURE)

        result: dict = {_STATE_CONTEXT_KEY: state_to_dict(final_state)}
        if decision.kind == DecisionKind.COMPLETE:
            result["supervisor_result"] = decision.result
        elif decision.kind == DecisionKind.WAIT:
            # Deliberately carried in `result`, not `error` - ActionOutput's
            # own docstring reserves `error` for FAILURE/RETRY only, and
            # WaitForEventAction's own PENDING return sets no error either
            # (see actions/wait_for_event.py). A WAIT is not an error
            # condition; `wait_reason` is here purely for debugging/
            # explainability, mirroring how `decision.reason` is already
            # preserved losslessly inside the serialized SupervisionState
            # itself either way.
            result["wait_reason"] = decision.reason

        error = decision.error if decision.kind in (DecisionKind.FAIL, DecisionKind.ABORT) else None

        return ActionOutput(status=outcome, result=result, error=error)


# Idempotent, not an unconditional register_action() call - same
# defensive idiom RecordExecutionAction already established (safe to
# import this module more than once in a process, and safe against a
# test that clears ACTION_REGISTRY for isolation and re-imports).
if not is_action_registered(SUPERVISOR_INVOCATION_ACTION_KEY):
    register_action(SUPERVISOR_INVOCATION_ACTION_KEY, SupervisorInvocationAction())
