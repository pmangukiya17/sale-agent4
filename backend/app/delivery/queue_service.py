"""
Human-triggered single-item queue operations - Cancel and Retry Now.
Deliberately separate from campaign_service (campaign-level, batch
operations) and dispatch_service (worker-triggered, the actual send).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.delivery_campaign import DeliveryCampaign
from app.models.delivery_event import DeliveryEvent
from app.models.delivery_queue_item import DeliveryQueueItem
from app.models.enums import DeliveryCampaignStatus, DeliveryEventType, DeliveryQueueItemStatus

_CANCELLABLE_STATUSES = {DeliveryQueueItemStatus.QUEUED, DeliveryQueueItemStatus.SCHEDULED, DeliveryQueueItemStatus.RETRY}
_RETRYABLE_STATUSES = {DeliveryQueueItemStatus.FAILED, DeliveryQueueItemStatus.RETRY}


class QueueServiceError(Exception):
    """Raised for anything the API layer should turn into a 400 - item
    not found, or an operation attempted from a state that doesn't allow
    it (e.g. cancelling an already-SENT item)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log_event(db: Session, queue_item_id: uuid.UUID, event_type: DeliveryEventType, detail: dict | None = None) -> None:
    db.add(DeliveryEvent(delivery_queue_item_id=queue_item_id, event_type=event_type, detail=detail))


def cancel_queue_item(db: Session, item_id: uuid.UUID, reason: str | None = None) -> DeliveryQueueItem:
    item = _get_item_or_raise(db, item_id)
    if item.status not in _CANCELLABLE_STATUSES:
        raise QueueServiceError(f"DeliveryQueueItem {item_id} cannot be cancelled from status '{item.status.value}'")
    item.status = DeliveryQueueItemStatus.CANCELLED
    item.cancelled_reason = reason
    _log_event(db, item.id, DeliveryEventType.CANCELLED, detail={"reason": reason} if reason else None)
    db.commit()
    db.refresh(item)
    return item


def retry_now(db: Session, item_id: uuid.UUID) -> DeliveryQueueItem:
    """Forces an immediate retry, bypassing whatever the scheduler had
    assigned. Does NOT reset attempt_count - a manual retry still counts
    toward max_attempts, so a genuinely broken address doesn't get
    infinite manual retries either.

    Root cause found during M5 Layer 7 verification: a retryable item is,
    by definition, FAILED - and FAILED is a terminal status. If this item
    was its campaign's last non-terminal item,
    campaign_service.maybe_mark_completed already flipped the campaign to
    COMPLETED the moment it failed (dispatch_service calls that after
    every terminal transition). Un-terminating the item here without also
    un-completing the campaign would leave it stuck: the campaign's
    status is checked FIRST in dispatch_service.dispatch() (before the
    connection/rate-limit checks), and a non-ACTIVE campaign there means
    "requeue 5 minutes out, don't dispatch" - forever, since nothing else
    would ever flip the campaign back to ACTIVE on its own. This mirrors
    maybe_mark_completed's own discipline, applied in the opposite
    direction, and only ever fires for COMPLETED (a CANCELLED campaign's
    items are already CANCELLED themselves by cancel_campaign, and
    CANCELLED is not in _RETRYABLE_STATUSES, so retry_now can never apply
    to one)."""
    item = _get_item_or_raise(db, item_id)
    if item.status not in _RETRYABLE_STATUSES:
        raise QueueServiceError(f"DeliveryQueueItem {item_id} cannot be retried from status '{item.status.value}'")
    item.status = DeliveryQueueItemStatus.SCHEDULED
    item.scheduled_send_at = _now()
    item.last_error = None
    _log_event(db, item.id, DeliveryEventType.SCHEDULED, detail={"reason": "manual_retry_now"})

    campaign = db.get(DeliveryCampaign, item.delivery_campaign_id)
    if campaign is not None and campaign.status == DeliveryCampaignStatus.COMPLETED:
        campaign.status = DeliveryCampaignStatus.ACTIVE

    db.commit()
    db.refresh(item)
    return item


def _get_item_or_raise(db: Session, item_id: uuid.UUID) -> DeliveryQueueItem:
    item = db.get(DeliveryQueueItem, item_id)
    if item is None:
        raise QueueServiceError(f"DeliveryQueueItem {item_id} not found")
    return item
