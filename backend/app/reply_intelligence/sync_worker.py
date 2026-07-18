"""
Mailbox sync worker: M6.2's own standalone polling process - a NEW,
second background worker alongside app/delivery/worker.py (M5's Delivery
worker), same image, different command (see docker-compose.yml's
mailbox_sync_worker service). Two responsibilities, kept as thin as
delivery/worker.py's own:

1. Each tick: for every ProviderConnection that is CONNECTED, whose
   registered provider implements IncrementalSyncCapable, AND already has
   read_scopes granted (see has_read_scope below) - call that provider's
   fetch_messages_incremental() and persist whatever comes back as new
   EmailMessage/Attachment rows (conversation_id = NULL, see
   email_message.py's docstring for the full lifecycle), then advance
   MailboxSyncState.cursor.
2. Never builds a Conversation, never assigns conversation_id, never
   touches ConversationParticipant - that is M6.3's job entirely, per
   explicit scope exclusion for this milestone. This worker's only write
   targets are EmailMessage, Attachment, and MailboxSyncState.

KNOWN GAP, disclosed rather than silently worked around: read_scopes
(Mail.Read) is requested via Reconnect using a caller-supplied scope list
- connection_service.build_reconnect_authorize_url already supports this,
it does not hardcode send_scopes - but M6.2's explicit implementation
scope, as given, does NOT include building the UI/route that actually
drives a Reconnect call with read_scopes instead of send_scopes. Until
that small follow-up exists, a ProviderConnection created through this
system's current UI only ever has send_scopes granted - has_read_scope()
below will correctly return False for every real connection today,
meaning this worker's per-tick loop finds zero eligible connections in
practice. The sync ENGINE itself (this file, the Outlook provider
implementation, the schema) is complete and independently verifiable
(unit tests + a real, isolated Graph delta call against a manually-scoped
credential) without that route existing - flagged here for the user to
decide whether to authorize as a small immediate follow-up or defer it.

Duplicate handling relies on the SAME partial unique index migration 0009
already created (uq_email_messages_connection_internet_message_id) - each
message insert happens inside its own SAVEPOINT (db.begin_nested()) so a
single duplicate (already-synced) message never aborts the rest of that
tick's batch, mirroring dispatch_service's own "one item's failure must
never poison the rest" discipline, applied here at per-message
granularity instead of per-queue-item.

Crash-safe checkpointing: MailboxSyncState.cursor is only advanced AFTER
every message from a tick has been committed - a crash mid-tick leaves
the cursor at its old value, so the next tick simply re-fetches (and
safely re-skips duplicates of, via the same dedup index) whatever was
already inserted before the crash. This trades a small amount of
redundant work for the guarantee that a crash can never silently skip a
message.

Same third-process-entrypoint mapper-registration requirement as
app/delivery/worker.py and tests/test_conversation_models.py (see either
docstring for the full explanation) - `from app.db import base as _base`
below is required, not optional decoration.
"""
import logging
import time as time_module
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import base as _base  # noqa: F401  (imports every model so relationship() string refs resolve - see module docstring)
from app.db.session import SessionLocal
from app.delivery.connection_service import ConnectionError_, refresh_credential_if_needed
from app.delivery.credentials.registry import get_credential_store
from app.delivery.providers.base import (
    IncrementalSyncCapable,
    ProviderAuthError,
    ProviderSyncError,
    provider_supports_capability,
)
from app.delivery.providers.registry import get_provider
from app.models.attachment import Attachment
from app.models.email_message import EmailMessage
from app.models.enums import MailboxSyncStatus, ProviderConnectionStatus
from app.models.mailbox_sync_state import MailboxSyncState
from app.models.provider_connection import ProviderConnection
from app.reply_intelligence.normalize import raw_attachment_to_kwargs, raw_message_to_email_message_kwargs

logger = logging.getLogger("sales_agent.mailbox_sync_worker")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def has_read_scope(connection: ProviderConnection, provider) -> bool:
    """Whether this connection's granted scopes already cover whatever
    the provider's IncrementalSyncCapable implementation requires (see
    IncrementalSyncCapable.read_scopes's docstring). Returns False (a
    legitimate "not eligible for sync yet" state, not an error) for a
    provider that doesn't implement IncrementalSyncCapable at all, or one
    that does but this connection was never granted read_scopes."""
    if not provider_supports_capability(provider, IncrementalSyncCapable):
        return False
    granted = set(connection.scopes_granted or [])
    return set(provider.read_scopes).issubset(granted)


def _get_or_create_sync_state(db: Session, connection_id: uuid.UUID) -> MailboxSyncState:
    state = db.scalar(select(MailboxSyncState).where(MailboxSyncState.provider_connection_id == connection_id))
    if state is None:
        state = MailboxSyncState(provider_connection_id=connection_id)
        db.add(state)
        db.flush()
    return state


def _persist_message(db: Session, provider_connection: ProviderConnection, raw, synced_at: datetime) -> bool:
    """Inserts one EmailMessage (+ its Attachments) inside its own
    SAVEPOINT so a duplicate (caught by migration 0009's partial unique
    index) never aborts the rest of the tick's batch. Returns True if
    inserted, False if skipped as a duplicate."""
    kwargs = raw_message_to_email_message_kwargs(
        raw,
        company_profile_id=provider_connection.company_profile_id,
        provider_connection_id=provider_connection.id,
        provider_key=provider_connection.provider_key,
        synced_at=synced_at,
    )
    try:
        with db.begin_nested():
            email_message = EmailMessage(**kwargs)
            db.add(email_message)
            db.flush()
            for raw_attachment in raw.attachments:
                db.add(Attachment(email_message_id=email_message.id, **raw_attachment_to_kwargs(raw_attachment)))
        return True
    except IntegrityError:
        # Real, expected case - the partial unique index on
        # (provider_connection_id, internet_message_id) rejected an
        # already-synced message (e.g. a crash-recovery re-fetch, or this
        # tick re-requested a page from before the cursor last advanced -
        # see module docstring). Not worth logging above debug level.
        logger.debug("Skipped duplicate EmailMessage for connection %s", provider_connection.id)
        return False


def sync_one_connection(db: Session, connection: ProviderConnection) -> int:
    """Runs one sync tick for one connection. Returns the number of new
    EmailMessage rows inserted (0 is a normal, common outcome - a quiet
    inbox - not an error)."""
    provider = get_provider(connection.provider_key)
    sync_state = _get_or_create_sync_state(db, connection.id)
    db.commit()

    credential_store = get_credential_store()
    try:
        credential_payload = refresh_credential_if_needed(db, credential_store, provider, connection)
    except ConnectionError_ as exc:
        connection.status = ProviderConnectionStatus.EXPIRED
        connection.last_verification_detail = str(exc)
        sync_state.last_sync_status = MailboxSyncStatus.ERROR
        sync_state.last_sync_detail = f"Could not obtain a usable credential: {exc}"
        sync_state.attempt_count += 1
        db.commit()
        return 0

    was_initial_sync = sync_state.cursor is None
    try:
        result = provider.fetch_messages_incremental(
            credential_payload, sync_state.cursor, settings.MAILBOX_SYNC_MAX_RESULTS_PER_TICK
        )
    except ProviderAuthError as exc:
        connection.status = ProviderConnectionStatus.EXPIRED
        connection.last_verification_detail = str(exc)
        sync_state.last_sync_status = MailboxSyncStatus.ERROR
        sync_state.last_sync_detail = str(exc)
        sync_state.attempt_count += 1
        db.commit()
        return 0
    except ProviderSyncError as exc:
        sync_state.last_sync_status = MailboxSyncStatus.ERROR
        sync_state.last_sync_detail = str(exc)
        sync_state.attempt_count += 1
        db.commit()
        return 0

    synced_at = _now()
    inserted = 0
    for raw in result.messages:
        if _persist_message(db, connection, raw, synced_at):
            inserted += 1
    db.commit()

    # Checkpoint LAST, after every message from this tick is durably
    # committed - see module docstring's crash-safety note.
    sync_state.cursor = result.next_cursor
    sync_state.last_synced_at = synced_at
    sync_state.last_sync_status = MailboxSyncStatus.OK
    sync_state.last_sync_detail = None
    sync_state.attempt_count = 0
    if was_initial_sync:
        sync_state.sync_window_start = synced_at
    db.commit()

    return inserted


def run_one_tick() -> int:
    """One pass over every eligible ProviderConnection. Returns the total
    number of new EmailMessage rows inserted across all connections."""
    db = SessionLocal()
    try:
        connections = list(
            db.scalars(select(ProviderConnection).where(ProviderConnection.status == ProviderConnectionStatus.CONNECTED))
        )
        eligible_ids = []
        for connection in connections:
            try:
                provider = get_provider(connection.provider_key)
            except KeyError:
                continue
            if has_read_scope(connection, provider):
                eligible_ids.append(connection.id)
    finally:
        db.close()

    total_inserted = 0
    for connection_id in eligible_ids:
        # Fresh session per connection - one connection's failure must
        # never poison the transaction state for the next one, same
        # discipline as delivery/worker.py's per-item session.
        db = SessionLocal()
        try:
            connection = db.get(ProviderConnection, connection_id)
            if connection is not None:
                total_inserted += sync_one_connection(db, connection)
        except Exception:  # noqa: BLE001 - the worker loop must survive one bad connection
            logger.exception("Unhandled error syncing ProviderConnection %s", connection_id)
            db.rollback()
        finally:
            db.close()

    return total_inserted


def run_forever() -> None:  # pragma: no cover - the loop itself isn't unit-testable
    logger.info(
        "Mailbox sync worker starting - poll_interval=%ss max_results_per_tick=%s",
        settings.MAILBOX_SYNC_POLL_INTERVAL_SECONDS,
        settings.MAILBOX_SYNC_MAX_RESULTS_PER_TICK,
    )
    while True:
        try:
            inserted = run_one_tick()
            if inserted:
                logger.info("Synced %d new message(s)", inserted)
        except Exception:  # noqa: BLE001 - one bad tick must never kill the worker process
            logger.exception("Unhandled error in mailbox sync worker tick")
        time_module.sleep(settings.MAILBOX_SYNC_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
