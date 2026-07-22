"""
Pure relationship-stage state machine + Task-suggestion rules - CRM
Automation milestone. No database session, no model imports beyond the
two enums these functions reason over - every function here is a plain,
deterministic value transformation, unit-testable with zero fixtures
(see tests/test_crm_automation_state_machine.py).

Relationship stage mapping - approved, narrowed to only what real data
in this codebase can support today (the original architecture doc's
mapping assumed an AI intent/extraction pipeline M6.4 was explicitly
NOT built with - see this package's own docstring):

    COLD        --outbound_sent-->              CONTACTED
    CONTACTED   --inbound_reply (any)-->         ENGAGED
    ENGAGED     --inbound_reply, POSITIVE-->     QUALIFIED
    QUALIFIED   --manual_advance (human only)--> NEGOTIATION

No rule ever advances a Prospect INTO NEGOTIATION automatically - that
transition exists in RelationshipStage but this state machine has no
trigger that produces it; only a human action (a future, separate API
call this milestone does not build) can. An inbound_reply that is not
POSITIVE (NEGATIVE/NEUTRAL/OUT_OF_OFFICE) while ENGAGED produces no
transition at all - "no rule fired" means "stay at the current stage,"
never an error and never a guess.
"""
import enum
from dataclasses import dataclass

from app.models.enums import RelationshipStage, ReplyStatus, TaskPriority


class RelationshipStageTrigger(str, enum.Enum):
    """The only three real facts this state machine reacts to - see this
    module's own docstring for exactly which call site produces each
    one. Deliberately not open-ended; adding a new trigger here is a
    conscious code change, mirroring every other closed-vocabulary enum
    in this codebase."""

    OUTBOUND_SENT = "outbound_sent"
    INBOUND_REPLY = "inbound_reply"
    MANUAL_ADVANCE = "manual_advance"


def next_relationship_stage(
    current_stage: RelationshipStage,
    trigger: RelationshipStageTrigger,
    *,
    reply_status: ReplyStatus | None = None,
) -> RelationshipStage | None:
    """Returns the new stage this (current_stage, trigger) combination
    deterministically produces, or None if no rule matches - meaning
    "no transition happens," not an error. reply_status is only ever
    consulted for the ENGAGED -> QUALIFIED rule; every other rule ignores
    it entirely, so passing it for an OUTBOUND_SENT/MANUAL_ADVANCE call is
    harmless."""
    if trigger == RelationshipStageTrigger.OUTBOUND_SENT and current_stage == RelationshipStage.COLD:
        return RelationshipStage.CONTACTED

    if trigger == RelationshipStageTrigger.INBOUND_REPLY:
        if current_stage == RelationshipStage.CONTACTED:
            return RelationshipStage.ENGAGED
        if current_stage == RelationshipStage.ENGAGED and reply_status == ReplyStatus.POSITIVE:
            return RelationshipStage.QUALIFIED
        return None

    if trigger == RelationshipStageTrigger.MANUAL_ADVANCE and current_stage == RelationshipStage.QUALIFIED:
        return RelationshipStage.NEGOTIATION

    return None


@dataclass(frozen=True)
class TaskSuggestion:
    """What app.crm_automation.service needs to create one Task row -
    deliberately just these three fields, mirroring
    ReplyClassificationResult's own minimal shape (see
    app/reply_intelligence/classifiers/base.py)."""

    suggested_action: str
    priority: TaskPriority
    source_event_type: str


def suggested_task_for_reply(
    reply_status: ReplyStatus,
    needs_human_review: bool,
    *,
    advanced_to_qualified: bool,
) -> TaskSuggestion | None:
    """Deterministic Task-suggestion rules over exactly the real signals
    M6.4's classifier and this module's own state machine produce -
    never an inferred "intent" or "extracted buyer request" (neither
    exists in this codebase's actual data). Returns None when no
    real signal warrants surfacing a Recommended Action (e.g. a plain
    NEUTRAL reply that didn't advance the stage and doesn't need
    review) - a Task is only ever created for a genuine, explainable
    reason, never to have something to show.

    Priority order (a reply can only ever match ONE of these - checked
    top to bottom): needing human review is always the most urgent
    signal, regardless of classification; a stage advance to QUALIFIED
    is the next most actionable; OUT_OF_OFFICE is informational only,
    never a Task (nothing for a human to act on); everything else
    (NEGATIVE/NEUTRAL without needs_human_review, which per M6.4's own
    mapping cannot actually occur today, but this function does not
    assume that invariant) produces no suggestion."""
    if needs_human_review:
        return TaskSuggestion(
            suggested_action=f"Review this reply - classified {reply_status.value.upper()} and flagged for human review.",
            priority=TaskPriority.HIGH,
            source_event_type="reply_classified",
        )

    if advanced_to_qualified:
        return TaskSuggestion(
            suggested_action="Prospect replied positively and reached Qualified - consider scheduling the next step.",
            priority=TaskPriority.NORMAL,
            source_event_type="relationship_stage_advanced",
        )

    return None
