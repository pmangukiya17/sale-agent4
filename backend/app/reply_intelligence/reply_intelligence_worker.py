"""
Reply Intelligence: M6.4's own standalone polling process - a FOURTH
background worker (alongside app/delivery/worker.py,
app/reply_intelligence/sync_worker.py, app/reply_intelligence/
thread_builder.py). Same single-instance, sequential-loop, fresh-
SessionLocal()-per-item pattern as all three - see thread_builder.py's
own docstring for the disclosed SKIP-LOCKED simplification, which
applies identically here.

Pipeline position (per the approved M6.4 design):

    Mailbox Sync -> Thread Builder -> Reply Intelligence -> Conversation updated

Reply Intelligence is data-coupled to Thread Builder exactly the way
Thread Builder is data-coupled to Mailbox Sync: no direct call, only a
shared state read through the database. Its candidate query
(_conversation_ids_with_inbound_replies below) can only ever see
EmailMessage rows that already have conversation_id set, because it
starts from "does an inbound message exist for this conversation" - a
message Thread Builder has not yet threaded is structurally invisible to
this worker, satisfying "only processes messages that already have
conversation_id" by construction, not by an extra filter that has to be
remembered.

Hard boundaries (explicit M6.4 scope): this worker NEVER writes
EmailMessage (not conversation_id, not any other column) and NEVER
writes anything outbound-related (DeliveryQueueItem, dispatch_service).
It writes exactly four Conversation columns:
reply_status/last_reply_at/last_reply_from/needs_human_review. Thread
Builder remains the sole owner of conversation assignment; nothing here
can affect it even by a future bug, because this module has no code path
that touches EmailMessage.conversation_id.

Cursor / idempotency design (M6.4 architecture round, explicit
correction from an earlier draft that would have compared
EmailMessage.received_at against Conversation.last_reply_at): worker
progress is NOT tracked against any business field. last_reply_at is a
business timestamp (when did the most recent reply actually happen) and
must never double as technical cursor state. Instead, this worker does a
full, cheap recompute every tick: every Conversation with at least one
inbound, threaded EmailMessage is reclassified from its latest inbound
message, every time. This is correct and genuinely idempotent (rerunning
with unchanged data produces identical writes, not just "no error") at
essentially zero cost, because the MVP rule-based classifier makes no
external calls - see rules_classifier.py. No new tracking column exists
anywhere for this, per the explicit instruction to prefer no additional
tracking over overloading a business field. If a future AI-backed
classifier makes this recompute non-trivial (real per-call latency/cost,
or conversation volume grows large), the natural additive fix is a
dedicated cursor table mirroring MailboxSyncState (one row per
Conversation, holding e.g. last_processed_message_id) - not needed today
and deliberately not built ahead of that need.

Same third-process-entrypoint mapper-registration requirement as every
other standalone worker in this codebase - `from app.db import base as
_base` below is required, not optional decoration.

CRM AUTOMATION MILESTONE ADDITION: process_one_conversation() now also
calls app.crm_automation.service.record_inbound_reply_classified()
right after writing the four Conversation fields above, in the same
transaction (isolated in its own SAVEPOINT - see that call site's own
comment). This advances Prospect.relationship_stage (CONTACTED ->
ENGAGED on any reply, ENGAGED -> QUALIFIED on ReplyStatus.POSITIVE),
writes Prospect/ProspectContact.last_replied_at, and creates a Task
(Recommended Action) when the deterministic suggestion rules warrant
one. This worker still NEVER writes EmailMessage or touches
conversation_id - that boundary is unchanged; the new call only ever
reads the Conversation/EmailMessage this worker already loaded and
writes to Prospect/ProspectContact/Task, a disjoint set of tables.
"""
import logging
import time as time_module

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.text_extraction import extract_plain_text
from app.crm_automation.service import record_inbound_reply_classified
from app.db import base as _base  # noqa: F401  (imports every model so relationship() string refs resolve - see module docstring)
from app.db.session import SessionLocal
from app.models.conversation import Conversation
from app.models.email_message import EmailMessage
from app.models.enums import MessageDirection
from app.reply_intelligence.classifiers.base import ReplyClassificationInput
from app.reply_intelligence.classifiers.registry import get_reply_classifier

logger = logging.getLogger("sales_agent.reply_intelligence_worker")


def _conversation_ids_with_inbound_replies(db: Session) -> list:
    """Every Conversation that has at least one inbound, threaded
    EmailMessage - the FULL candidate set, recomputed every tick (see
    module docstring for why there is no incremental/cursor filter
    here). Deliberately global, not scoped to one company, matching
    every other worker's candidate query in this codebase (e.g.
    thread_builder.run_one_tick())."""
    return list(
        db.scalars(
            select(EmailMessage.conversation_id)
            .where(EmailMessage.direction == MessageDirection.INBOUND, EmailMessage.conversation_id.isnot(None))
            .distinct()
        )
    )


def _latest_inbound_message(db: Session, conversation_id) -> EmailMessage | None:
    return db.scalars(
        select(EmailMessage)
        .where(EmailMessage.conversation_id == conversation_id, EmailMessage.direction == MessageDirection.INBOUND)
        .order_by(EmailMessage.received_at.desc().nullslast(), EmailMessage.sent_at.desc().nullslast())
        .limit(1)
    ).first()


def process_one_conversation(db: Session, conversation_id) -> bool:
    """Classifies the latest inbound message for one Conversation and
    writes the four M6.4 fields. Returns True if a Conversation was
    actually updated (for logging/test counts), False for the defensive
    case where the candidate row has no matching message by the time this
    runs (e.g. deleted between the candidate query and here)."""
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        return False

    message = _latest_inbound_message(db, conversation_id)
    if message is None:
        return False

    classifier = get_reply_classifier()
    result = classifier.classify(
        ReplyClassificationInput(
            text=extract_plain_text(message),
            from_email=message.from_email,
            received_at=message.received_at,
        )
    )

    conversation.reply_status = result.reply_status
    conversation.last_reply_at = message.received_at or message.sent_at
    conversation.last_reply_from = message.from_email
    conversation.needs_human_review = result.needs_human_review

    # CRM Automation milestone: same transaction, before this function's
    # own db.commit() below - advances relationship_stage, writes
    # last_replied_at, and creates a Task when the deterministic
    # suggestion rules warrant one. See app.crm_automation's own
    # docstring for why this is a plain synchronous call, not a Workflow
    # Engine Action. Isolated in its own SAVEPOINT, same discipline as
    # dispatch_service.py's _record_crm_automation_for_send - a bug here
    # must roll back only this nested transaction, never prevent this
    # Conversation's real classification (already set above) from being
    # committed, and never leave the outer transaction in Postgres's
    # aborted-transaction state for the db.commit() below.
    try:
        with db.begin_nested():
            record_inbound_reply_classified(db, conversation, message, result.reply_status, result.needs_human_review)
    except Exception:  # noqa: BLE001 - the classification above must still commit even if CRM automation fails
        logger.exception("CRM automation failed for Conversation %s - reply classification will still be committed.", conversation_id)

    db.commit()
    return True


def run_one_tick() -> dict[str, int]:
    """One full pass: reclassify every Conversation with at least one
    inbound, threaded message. Returns counts for logging/tests."""
    db = SessionLocal()
    try:
        candidate_ids = _conversation_ids_with_inbound_replies(db)
    finally:
        db.close()

    counts = {"classified": 0}
    for conversation_id in candidate_ids:
        # Fresh session per conversation - one conversation's failure must
        # never poison the transaction state for the next one, same
        # discipline as every other worker loop in this codebase.
        db = SessionLocal()
        try:
            if process_one_conversation(db, conversation_id):
                counts["classified"] += 1
        except Exception:  # noqa: BLE001 - the worker loop must survive one bad conversation
            logger.exception("Unhandled error classifying Conversation %s", conversation_id)
            db.rollback()
        finally:
            db.close()

    return counts


def run_forever() -> None:  # pragma: no cover - the loop itself isn't unit-testable
    logger.info(
        "Reply Intelligence starting - poll_interval=%ss classifier_backend=%s",
        settings.REPLY_INTELLIGENCE_POLL_INTERVAL_SECONDS,
        settings.REPLY_CLASSIFIER_BACKEND,
    )
    while True:
        try:
            counts = run_one_tick()
            if any(counts.values()):
                logger.info("Reply Intelligence tick: %s", counts)
        except Exception:  # noqa: BLE001 - one bad tick must never kill the worker process
            logger.exception("Unhandled error in Reply Intelligence tick")
        time_module.sleep(settings.REPLY_INTELLIGENCE_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
