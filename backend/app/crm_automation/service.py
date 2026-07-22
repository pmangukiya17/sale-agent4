"""
CRM Automation service - the only module in this package that touches a
Session. Called from two existing, already-synchronous call sites (see
this package's own __init__.py docstring); every function here performs
its writes in the CALLER's transaction and never commits - the caller's
own existing db.commit() (already present at both call sites before this
milestone) is what makes these writes atomic with the domain write that
triggered them, the same transactional-outbox discipline
publish_event() itself already documents.

Both functions below are intentionally defensive about missing data
(no Prospect resolved, no ProspectContact known) rather than raising -
a CRM-automation bookkeeping gap must never turn into an unhandled
exception that could interrupt a real send or a real reply
classification; the same "never let secondary bookkeeping undo the
real action" discipline dispatch_service.py's own
_record_outbound_conversation already established for M6.3.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.crm_automation.state_machine import (
    RelationshipStageTrigger,
    next_relationship_stage,
    suggested_task_for_reply,
)
from app.models.conversation import Conversation
from app.models.email_message import EmailMessage
from app.models.enums import RelationshipStage, ReplyStatus, TaskStatus
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.prospect_timeline_event import ProspectTimelineEvent
from app.models.task import Task
from app.workflow_engine.events import publish_event

logger = logging.getLogger("sales_agent.crm_automation")

# Published on the same Event Backbone Notifications/Realtime/the
# Workflow Engine's own Event Dispatcher already share - see this
# package's own docstring for why no BuiltinWorkflowDefinition consumes
# these today, and why that's fine.
RELATIONSHIP_STAGE_ADVANCED_EVENT_TYPE = "prospect.relationship_stage_advanced"
TASK_CREATED_EVENT_TYPE = "task.created"

_EVENT_SOURCE = "app.crm_automation.service"


def _advance_relationship_stage(
    db: Session,
    prospect: Prospect,
    trigger: RelationshipStageTrigger,
    *,
    reply_status: ReplyStatus | None = None,
) -> RelationshipStage | None:
    """Shared by both public functions below - applies
    next_relationship_stage()'s decision, if any, and logs/publishes it.
    Returns the new stage (or None if no transition occurred), so callers
    can use it to decide whether a stage-advance Task suggestion applies."""
    old_stage = prospect.relationship_stage
    new_stage = next_relationship_stage(old_stage, trigger, reply_status=reply_status)
    if new_stage is None:
        return None

    prospect.relationship_stage = new_stage
    db.add(
        ProspectTimelineEvent(
            prospect_id=prospect.id,
            event_type="relationship_stage_advanced",
            actor="system",
            payload={"from": old_stage.value, "to": new_stage.value, "trigger": trigger.value},
        )
    )
    publish_event(
        db,
        event_type=RELATIONSHIP_STAGE_ADVANCED_EVENT_TYPE,
        company_profile_id=prospect.company_profile_id,
        source=_EVENT_SOURCE,
        subject_type="prospect",
        subject_id=prospect.id,
        payload={"from": old_stage.value, "to": new_stage.value, "trigger": trigger.value},
    )
    return new_stage


def record_outbound_sent(
    db: Session,
    prospect: Prospect | None,
    prospect_contact: ProspectContact | None,
    sent_at: datetime,
) -> None:
    """Called from app.delivery.dispatch_service.dispatch(), right after
    a send succeeds (same transaction as item.status = SENT and
    _record_outbound_conversation). Advances COLD -> CONTACTED and writes
    last_contacted_at. prospect may be None defensively (should not
    happen in practice - DeliveryQueueItem.prospect_id is NOT NULL - but
    this function must never raise if it somehow is)."""
    if prospect is None:
        logger.warning("record_outbound_sent called with prospect=None - skipping CRM automation for this send.")
        return

    prospect.last_contacted_at = sent_at
    if prospect_contact is not None:
        prospect_contact.last_contacted_at = sent_at

    db.add(
        ProspectTimelineEvent(
            prospect_id=prospect.id,
            event_type="outbound_sent",
            actor="system",
            payload={"sent_at": sent_at.isoformat()},
        )
    )

    _advance_relationship_stage(db, prospect, RelationshipStageTrigger.OUTBOUND_SENT)


def record_inbound_reply_classified(
    db: Session,
    conversation: Conversation,
    message: EmailMessage,
    reply_status: ReplyStatus,
    needs_human_review: bool,
) -> None:
    """Called from app.reply_intelligence.reply_intelligence_worker's
    process_one_conversation(), right after Conversation.reply_status/
    last_reply_at/last_reply_from/needs_human_review are set on the same
    Conversation instance, same transaction (that function's own
    db.commit() happens after this call returns).

    If conversation.prospect_id is None (an inbound message from an
    unrecognized sender - see Conversation's own docstring), this
    function does nothing: never silently create or advance a Prospect
    from an unresolved participant - identity resolution stays a
    human-confirmed action, the same boundary already held everywhere
    else in this system."""
    if conversation.prospect_id is None:
        return

    prospect = db.get(Prospect, conversation.prospect_id)
    if prospect is None:
        logger.warning("Conversation %s references Prospect %s which no longer exists - skipping CRM automation.", conversation.id, conversation.prospect_id)
        return

    replied_at = message.received_at or message.sent_at
    prospect.last_replied_at = replied_at

    contact: ProspectContact | None = None
    if conversation.prospect_contact_id is not None:
        contact = db.get(ProspectContact, conversation.prospect_contact_id)
        if contact is not None:
            contact.last_replied_at = replied_at

    db.add(
        ProspectTimelineEvent(
            prospect_id=prospect.id,
            event_type="inbound_reply_classified",
            actor="system",
            payload={
                "conversation_id": str(conversation.id),
                "reply_status": reply_status.value,
                "needs_human_review": needs_human_review,
            },
        )
    )

    new_stage = _advance_relationship_stage(
        db, prospect, RelationshipStageTrigger.INBOUND_REPLY, reply_status=reply_status
    )

    suggestion = suggested_task_for_reply(
        reply_status, needs_human_review, advanced_to_qualified=(new_stage == RelationshipStage.QUALIFIED)
    )
    if suggestion is None:
        return

    task = Task(
        company_profile_id=prospect.company_profile_id,
        prospect_id=prospect.id,
        prospect_contact_id=contact.id if contact is not None else None,
        conversation_id=conversation.id,
        suggested_action=suggestion.suggested_action,
        source_event_type=suggestion.source_event_type,
        priority=suggestion.priority,
        status=TaskStatus.PENDING,
    )
    db.add(task)
    db.flush()  # need task.id for publish_event's subject_id

    db.add(
        ProspectTimelineEvent(
            prospect_id=prospect.id,
            event_type="task_created",
            actor="system",
            payload={"task_id": str(task.id), "source_event_type": suggestion.source_event_type},
        )
    )
    publish_event(
        db,
        event_type=TASK_CREATED_EVENT_TYPE,
        company_profile_id=prospect.company_profile_id,
        source=_EVENT_SOURCE,
        subject_type="task",
        subject_id=task.id,
        payload={"prospect_id": str(prospect.id), "source_event_type": suggestion.source_event_type},
    )
