"""
RecordExecutionAction - M7.1 Part 2's pilot Action, kept permanently
useful beyond the pilot (per explicit design direction: this action is
not renamed or removed once the pilot workflow is superseded by richer
future workflows - it stays available as a generic "prove this step ran"
building block).

Deliberately the simplest possible real, registered Action: no domain
work, no external API, no AI. It never reads `context` for domain
meaning - it only reports that the engine actually invoked this step,
when, and for which instance/step. This is what validates the full
engine pipeline (Event -> Event Dispatcher -> WorkflowInstance -> Step
Runner -> Action -> completion) end to end against a REAL production
trigger, not just the synthetic fakes Part 1's own test suite used.

Writes into the two places the engine already persists Action results -
WorkflowStepInvocation.output (written by the Step Runner for every
attempt automatically, Part 1 Phase 5) and WorkflowInstance.context
(merged the same way). Deliberately creates no new database table - see
this package's own __init__.py for the "domain modules/action packages
register themselves" boundary this class is the first real example of.

Action key naming: "workflow." is this action's permanent namespace
prefix, distinct from "engine." (reserved for the engine's own built-in
pseudo-actions - see actions/base.py's WAIT_FOR_EVENT_ACTION_KEY) and
from any future domain prefix ("delivery.", "reply_intelligence.", etc.
for actions a specific domain module owns and self-registers). "workflow."
signals "a generic, reusable building block belonging to the workflow
system itself, not owned by one business domain" - chosen over "system."
as less likely to be misread as infrastructure/ops tooling.
"""
from datetime import datetime, timezone

from app.workflow_engine.actions.base import Action, ActionInput, ActionOutcome, ActionOutput
from app.workflow_engine.actions.registry import is_action_registered, register_action

RECORD_EXECUTION_ACTION_KEY = "workflow.record_execution"


class RecordExecutionAction(Action):
    """Always returns SUCCESS - there is no failure mode to exercise by
    design. `result` is entirely generic: it names which instance/step
    executed and when, never anything about what the instance's context
    contains."""

    def execute(self, input_data: ActionInput) -> ActionOutput:
        return ActionOutput(
            status=ActionOutcome.SUCCESS,
            result={
                "action_key": RECORD_EXECUTION_ACTION_KEY,
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "workflow_instance_id": str(input_data.workflow_instance_id),
                "step_id": input_data.step_id,
                "idempotency_key": input_data.idempotency_key,
            },
        )


# Idempotent, not an unconditional register_action() call - safe to
# import this module more than once in a process (module caching makes
# that a no-op for the class definition above regardless, but this guard
# also protects against a test explicitly re-invoking registration after
# clearing ACTION_REGISTRY for isolation, matching the exact defensive
# idiom app.workflow_engine.actions.registry.ensure_builtin_actions_registered()
# already established for the engine's own built-in action).
if not is_action_registered(RECORD_EXECUTION_ACTION_KEY):
    register_action(RECORD_EXECUTION_ACTION_KEY, RecordExecutionAction())
