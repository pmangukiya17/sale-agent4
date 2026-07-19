"""
Thread Builder: M6.3's own standalone polling process - a THIRD
background worker (alongside app/delivery/worker.py and
app/reply_intelligence/sync_worker.py). Explicitly approved as a
dedicated worker during M6.3's architecture round, in preference to
folding this logic into the mailbox sync worker: independent poll
cadence, independent failure/retry semantics/monitoring, and the ability
to re-run without re-triggering a sync tick - all needed for the bounded
"wait for a parent message to arrive" retry case (see thread_matching.py,
UNTHREADED_RETRY_WINDOW_MINUTES).

Single responsibility: claim EmailMessage rows with conversation_id IS
NULL and direction = inbound - outbound rows are NEVER in this queue,
because dispatch_service already assigns their conversation_id
synchronously at send time (see conversation_resolver.py) - and run
thread_matching.match_conversation() against each, then either attach it
to an existing Conversation, create a new one, or leave it (bounded,
self-limiting, no new status column) for a future pass.

Same single-instance, sequential-loop simplification already established
by the mailbox sync worker (no SELECT...FOR UPDATE SKIP LOCKED) - see
that module's own disclosed reasoning; this matches the actual
single-replica reality of every worker service in this project's
docker-compose.yml today. Adding row-level claiming is additive if this
worker is ever scaled to multiple replicas, not a redesign.

Same third-process-entrypoint mapper-registration requirement as every
other standalone worker in this codebase - `from app.db import base as
_base` below is required, not optional decoration (see
app/delivery/worker.py's own docstring for the original incident this
guards against).
"""
import logging
import time as time_module

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import base as _base  # noqa: F401  (imports every model so relationship() string refs resolve - see module docstring)
from app.db.session import SessionLocal
from app.models.email_message import EmailMessage
from app.models.enums import MessageDirection
from app.reply_intelligence.thread_matching import (
    create_conversation_for_unmatched_inbound,
    match_conversation,
    sync_participants_for_message,
)
from app.workflow_engine.events import publish_event

# M7.1 Part 2: the business-capability name this worker publishes events
# under - deliberately NOT "thread_builder" (an implementation detail
# that could change - e.g. this logic could someday move into the sync
# worker, or be split further - without the business meaning of "who
# published this" changing). "reply_intelligence" is the stable domain
# package this module already lives inside (app.reply_intelligence),
# matching this project's existing REPLY_CLASSIFIER_BACKEND/
# app.reply_intelligence.* naming.
_EVENT_SOURCE = "reply_intelligence"

# M7.1 Part 2: this project's first real, production Event. Published
# ONLY when create_conversation_for_unmatched_inbound() below actually
# creates a brand-new Conversation - never for the "matched an existing
# Conversation" branch above, which is a deliberate, load-bearing
# distinction (see tests/test_pilot_workflow_e2e.py's own negative-case
# test). subject_type/subject_id carry the new Conversation's identity
# so the Workflow Engine can correlate a resulting WorkflowInstance back
# to it - the Workflow Engine never interprets what "conversation" means,
# it only ever treats subject_type/subject_id as opaque correlation
# strings (see Event's own docstring).
CONVERSATION_CREATED_EVENT_TYPE = "conversation.created"

logger = logging.getLogger("sales_agent.thread_builder")


def process_one_message(db: Session, message: EmailMessage) -> str:
    """Runs the full matching decision for one message and applies it.
    Returns a short outcome label ("matched" / "created" / "waiting") for
    logging and tests - never raises for an ordinary matching outcome,
    only for a genuine unexpected error (left to the caller's try/except,
    same discipline as every other worker loop in this codebase)."""
    decision = match_conversation(db, message)

    if decision.conversation is not None:
        message.conversation_id = decision.conversation.id
        if message.sent_at is not None and (
            decision.conversation.last_message_at is None or message.sent_at > decision.conversation.last_message_at
        ):
            decision.conversation.last_message_at = message.sent_at
        sync_participants_for_message(db, decision.conversation, message)
        db.commit()
        return "matched"

    if decision.should_wait:
        # No changes were made - explicit no-op commit so the session
        # doesn't carry a dangling transaction into the next iteration.
        db.commit()
        return "waiting"

    conversation = create_conversation_for_unmatched_inbound(db, message)
    message.conversation_id = conversation.id
    sync_participants_for_message(db, conversation, message)
    # M7.1 Part 2: publish_event() only flushes - it never commits (see
    # its own docstring) - so this Event lands in the SAME transaction as
    # the Conversation/EmailMessage/participant writes above; the
    # db.commit() below is what makes all of them atomic together (the
    # transactional outbox pattern - if anything above this point were to
    # fail, the Event would never exist either).
    publish_event(
        db,
        event_type=CONVERSATION_CREATED_EVENT_TYPE,
        company_profile_id=conversation.company_profile_id,
        source=_EVENT_SOURCE,
        subject_type="conversation",
        subject_id=conversation.id,
    )
    db.commit()
    return "created"


def run_one_tick() -> dict[str, int]:
    """One pass over the current WHERE conversation_id IS NULL backlog
    (inbound only), up to THREAD_BUILDER_BATCH_SIZE messages. Returns
    counts per outcome so the caller (the loop, or a test) can log/assert
    on them."""
    db = SessionLocal()
    try:
        candidate_ids = list(
            db.scalars(
                select(EmailMessage.id)
                .where(EmailMessage.conversation_id.is_(None), EmailMessage.direction == MessageDirection.INBOUND)
                .order_by(EmailMessage.received_at.asc().nullslast(), EmailMessage.sent_at.asc().nullslast())
                .limit(settings.THREAD_BUILDER_BATCH_SIZE)
            )
        )
    finally:
        db.close()

    counts = {"matched": 0, "created": 0, "waiting": 0}
    for message_id in candidate_ids:
        # Fresh session per message - one message's failure must never
        # poison the transaction state for the next one, same discipline
        # as delivery/worker.py and sync_worker.py.
        db = SessionLocal()
        try:
            message = db.get(EmailMessage, message_id)
            if message is not None and message.conversation_id is None:
                outcome = process_one_message(db, message)
                counts[outcome] = counts.get(outcome, 0) + 1
        except Exception:  # noqa: BLE001 - the worker loop must survive one bad message
            logger.exception("Unhandled error threading EmailMessage %s", message_id)
            db.rollback()
        finally:
            db.close()

    return counts


def run_forever() -> None:  # pragma: no cover - the loop itself isn't unit-testable
    logger.info(
        "Thread Builder starting - poll_interval=%ss batch_size=%s",
        settings.THREAD_BUILDER_POLL_INTERVAL_SECONDS,
        settings.THREAD_BUILDER_BATCH_SIZE,
    )
    while True:
        try:
            counts = run_one_tick()
            if any(counts.values()):
                logger.info("Thread Builder tick: %s", counts)
        except Exception:  # noqa: BLE001 - one bad tick must never kill the worker process
            logger.exception("Unhandled error in Thread Builder tick")
        time_module.sleep(settings.THREAD_BUILDER_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
