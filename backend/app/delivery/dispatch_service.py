"""
dispatch_service: takes ONE already-claimed (status=SENDING) queue item
and actually sends it - nothing else. Deliberately separate from
worker.py (the polling loop) and scheduler/policy.py (which decided this
item should be claimed) per the explicit M5 refinement: queue management,
scheduling, and provider dispatch are three separate responsibilities.

Rate limiting is enforced HERE, at actual dispatch time, in addition to
the pacing schedule_campaign already assigned - a live rolling-window
count against DeliveryEvent, not just trusting that the assigned
scheduled_send_at values were correctly spaced. This is the real backstop
against two campaigns sharing one SendingProfile jointly exceeding its
caps (see campaign_service's disclosed scope limit).

DeliveryEvent(started) is written and committed BEFORE calling the
provider - so if the process crashes mid-send, the history at minimum
shows an attempt was in flight, rather than looking like nothing
happened. This is the best available mitigation for exactly-once delivery
without a provider-side idempotency key (Gmail/Graph don't offer one for
sending) - see worker.py's docstring for the stale-claim reconciliation
that handles the crash-recovery side of this.

M6.3 ADDITION - on a successful send, this module now also mirrors the
email into the M6 Conversation/EmailMessage/ConversationParticipant
schema (see conversation_resolver.py and email_message.py's own
docstrings), so Thread Builder has an outbound anchor to correlate a
future reply against. This is genuinely new write responsibility for
already-tagged M5 code - disclosed and approved as part of M6.3's
architecture, same category of change as the provider send() updates
(app/delivery/providers/outlook_provider.py, gmail_provider.py). It runs
inside its own SAVEPOINT (_record_outbound_conversation, below): the
email has ALREADY been sent by the time this code runs, so a bug in this
bookkeeping must never make DeliveryQueueItem look like the send itself
failed - it is logged, never raised, on failure.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.delivery import campaign_service
from app.delivery.connection_service import ConnectionError_, refresh_credential_if_needed
from app.delivery.context import DeliveryContext
from app.delivery.credentials.registry import get_credential_store
from app.delivery.providers.base import DeliverySendOutcome, ProviderAuthError, ProviderSendError
from app.delivery.providers.registry import get_provider
from app.models.delivery_campaign import DeliveryCampaign
from app.models.delivery_event import DeliveryEvent
from app.models.delivery_queue_item import DeliveryQueueItem
from app.models.email_message import EmailMessage
from app.models.enums import (
    ConversationParticipantRole,
    DeliveryCampaignStatus,
    DeliveryEventType,
    DeliveryQueueItemStatus,
    MessageDirection,
    ProviderConnectionStatus,
)
from app.models.provider_connection import ProviderConnection
from app.models.sending_profile import SendingProfile
from app.reply_intelligence.conversation_resolver import get_or_create_conversation_for_outbound, upsert_participant

logger = logging.getLogger("sales_agent.dispatch_service")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log_event(db: Session, queue_item_id: uuid.UUID, event_type: DeliveryEventType, detail: dict | None = None) -> None:
    db.add(DeliveryEvent(delivery_queue_item_id=queue_item_id, event_type=event_type, detail=detail))


def _sent_count_since(db: Session, sending_profile_id: uuid.UUID, since: datetime) -> int:
    return db.scalar(
        select(func.count())
        .select_from(DeliveryEvent)
        .join(DeliveryQueueItem, DeliveryEvent.delivery_queue_item_id == DeliveryQueueItem.id)
        .where(
            DeliveryQueueItem.sending_profile_id == sending_profile_id,
            DeliveryEvent.event_type == DeliveryEventType.SENT,
            DeliveryEvent.occurred_at >= since,
        )
    ) or 0


def _requeue_for_rate_limit(db: Session, item: DeliveryQueueItem, retry_after: datetime, reason: str) -> None:
    item.status = DeliveryQueueItemStatus.SCHEDULED
    item.scheduled_send_at = retry_after
    item.claimed_at = None
    _log_event(db, item.id, DeliveryEventType.SCHEDULED, detail={"reason": reason, "retry_after": retry_after.isoformat()})
    db.commit()


def dispatch(db: Session, item: DeliveryQueueItem) -> None:
    """item must already be in SENDING status (claimed by a
    SchedulingPolicy). Always leaves the item in a terminal-for-this-
    attempt state (SENT/FAILED) or re-scheduled (SCHEDULED/RETRY) - never
    leaves it sitting in SENDING when this function returns, so a crash
    INSIDE this function (not before it) is the only way a stale SENDING
    row can occur - which is exactly what worker.py's reconciliation pass
    exists to clean up."""
    campaign = db.get(DeliveryCampaign, item.delivery_campaign_id)
    if campaign is not None and campaign.status != DeliveryCampaignStatus.ACTIVE:
        _requeue_for_rate_limit(db, item, _now() + timedelta(minutes=5), reason=f"campaign_status_{campaign.status.value}")
        return

    sending_profile = db.get(SendingProfile, item.sending_profile_id)
    if sending_profile is None or not sending_profile.is_active:
        _requeue_for_rate_limit(db, item, _now() + timedelta(minutes=15), reason="sending_profile_inactive")
        return

    if sending_profile.hourly_limit is not None:
        sent_last_hour = _sent_count_since(db, sending_profile.id, _now() - timedelta(hours=1))
        if sent_last_hour >= sending_profile.hourly_limit:
            _requeue_for_rate_limit(db, item, _now() + timedelta(minutes=15), reason="hourly_limit_reached_at_dispatch")
            return
    if sending_profile.daily_limit is not None:
        sent_last_day = _sent_count_since(db, sending_profile.id, _now() - timedelta(days=1))
        if sent_last_day >= sending_profile.daily_limit:
            _requeue_for_rate_limit(db, item, _now() + timedelta(hours=1), reason="daily_limit_reached_at_dispatch")
            return

    connection = db.get(ProviderConnection, sending_profile.provider_connection_id) if sending_profile.provider_connection_id else None
    if connection is None or connection.status not in (ProviderConnectionStatus.CONNECTED, ProviderConnectionStatus.EXPIRED):
        _fail_item(db, item, "SendingProfile has no usable ProviderConnection - connect or reconnect it first.", permanent=True)
        return

    provider = get_provider(connection.provider_key)
    credential_store = get_credential_store()
    try:
        credential_payload = refresh_credential_if_needed(db, credential_store, provider, connection)
    except ConnectionError_ as exc:
        connection.status = ProviderConnectionStatus.EXPIRED
        connection.last_verification_detail = str(exc)
        db.commit()
        _fail_item(db, item, f"Could not obtain a usable credential: {exc}", permanent=True)
        return

    context = DeliveryContext(
        queue_item=item, sending_profile=sending_profile, provider_connection=connection, credential_payload=credential_payload
    )

    _log_event(db, item.id, DeliveryEventType.STARTED)
    db.commit()

    try:
        outcome = provider.send(context)
    except ProviderAuthError as exc:
        connection.status = ProviderConnectionStatus.EXPIRED
        connection.last_verification_detail = str(exc)
        db.commit()
        _retry_or_fail(db, item, str(exc), permanent=False)
        return
    except ProviderSendError as exc:
        _retry_or_fail(db, item, str(exc), permanent=exc.permanent)
        return
    except Exception as exc:  # noqa: BLE001 - an unanticipated provider failure must not crash the worker loop
        _retry_or_fail(db, item, f"Unexpected error: {exc}", permanent=False)
        return

    item.status = DeliveryQueueItemStatus.SENT
    item.sent_at = _now()
    item.provider_message_id = outcome.provider_message_id
    item.claimed_at = None
    _log_event(db, item.id, DeliveryEventType.SENT, detail=outcome.detail)

    _record_outbound_conversation(db, item, sending_profile, connection, outcome)

    db.commit()
    campaign_service.maybe_mark_completed(db, item.delivery_campaign_id)


def _retry_or_fail(db: Session, item: DeliveryQueueItem, error_message: str, *, permanent: bool) -> None:
    item.attempt_count += 1
    item.last_error = error_message
    item.claimed_at = None
    if permanent or item.attempt_count >= item.max_attempts:
        item.status = DeliveryQueueItemStatus.FAILED
        _log_event(db, item.id, DeliveryEventType.FAILED, detail={"error": error_message, "attempt_count": item.attempt_count})
        db.commit()
        campaign_service.maybe_mark_completed(db, item.delivery_campaign_id)
    else:
        # Exponential-ish backoff: 2^attempt_count minutes, capped at 60.
        backoff_minutes = min(60, 2 ** item.attempt_count)
        item.status = DeliveryQueueItemStatus.RETRY
        item.scheduled_send_at = _now() + timedelta(minutes=backoff_minutes)
        _log_event(db, item.id, DeliveryEventType.RETRY, detail={"error": error_message, "attempt_count": item.attempt_count, "backoff_minutes": backoff_minutes})
        db.commit()


def _fail_item(db: Session, item: DeliveryQueueItem, error_message: str, *, permanent: bool) -> None:
    item.claimed_at = None
    _retry_or_fail(db, item, error_message, permanent=permanent)


def _record_outbound_conversation(
    db: Session,
    item: DeliveryQueueItem,
    sending_profile: SendingProfile,
    connection: ProviderConnection,
    outcome: DeliverySendOutcome,
) -> None:
    """M6.3: mirrors a just-sent email into Conversation/EmailMessage/
    ConversationParticipant - see this module's own docstring for why
    this exists and why it's isolated in a SAVEPOINT. item.sent_at must
    already be set by the caller (it is, by the time dispatch() reaches
    this call). Never raises - a failure here is logged and swallowed,
    since the actual send already succeeded and must not be undone by a
    secondary bookkeeping problem."""
    try:
        with db.begin_nested():
            assembled = (item.frozen_content or {}).get("assembled", {})
            conversation = get_or_create_conversation_for_outbound(
                db,
                company_profile_id=item.company_profile_id,
                provider_connection_id=connection.id,
                prospect_id=item.prospect_id,
                prospect_contact_id=item.prospect_contact_id,
                subject=assembled.get("subject"),
                sent_at=item.sent_at,
            )

            email_message = EmailMessage(
                conversation_id=conversation.id,
                company_profile_id=item.company_profile_id,
                provider_connection_id=connection.id,
                delivery_queue_item_id=item.id,
                provider=connection.provider_key,
                provider_message_id=outcome.provider_message_id,
                provider_thread_id=outcome.provider_thread_id,
                internet_message_id=outcome.internet_message_id,
                direction=MessageDirection.OUTBOUND,
                from_email=sending_profile.sender_email,
                from_name=sending_profile.sender_name,
                subject=assembled.get("subject"),
                body_text=assembled.get("body"),
                sent_at=item.sent_at,
                to_recipients=[{"email": item.recipient_email, "name": None}],
                cc_recipients=[],
                has_attachments=False,
            )
            db.add(email_message)
            db.flush()

            upsert_participant(
                db,
                conversation_id=conversation.id,
                email=item.recipient_email,
                name=None,
                role=ConversationParticipantRole.TO,
                prospect_contact_id=item.prospect_contact_id,
            )
            upsert_participant(
                db,
                conversation_id=conversation.id,
                email=sending_profile.sender_email,
                name=sending_profile.sender_name,
                role=ConversationParticipantRole.FROM_,
            )
    except Exception:  # noqa: BLE001 - see this function's own docstring: never let bookkeeping failure undo a real send
        logger.exception(
            "Failed to record outbound Conversation/EmailMessage for DeliveryQueueItem %s - the email was still sent successfully.",
            item.id,
        )
