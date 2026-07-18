import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import DeliveryQueueItemStatus
from app.schemas.delivery_event import DeliveryEventRead


class DeliveryQueueItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    delivery_campaign_id: uuid.UUID
    outreach_draft_id: uuid.UUID
    prospect_id: uuid.UUID
    prospect_contact_id: uuid.UUID
    company_profile_id: uuid.UUID
    sending_profile_id: uuid.UUID
    channel_key: str

    # frozen_content/frozen_draft_version are the snapshot actually being
    # sent - see the model's docstring on why this is never re-read live
    # from OutreachDraft. Exposed read-only; there is no update endpoint
    # for a queue item's content, only status-changing actions
    # (Cancel/Retry Now).
    frozen_content: dict[str, Any]
    frozen_draft_version: int
    recipient_email: str
    recipient_timezone: str | None

    status: DeliveryQueueItemStatus
    scheduled_send_at: datetime | None
    sent_at: datetime | None
    attempt_count: int
    max_attempts: int
    last_error: str | None
    provider_message_id: str | None
    # Set by the worker's SELECT...FOR UPDATE SKIP LOCKED claim, cleared
    # on completion - exposed so a stuck-item diagnostic view can show
    # "claimed 40 minutes ago, still SENDING" before the worker's own
    # stale-claim reconciliation pass would reset it. See
    # DeliveryQueueItem's model docstring.
    claimed_at: datetime | None
    cancelled_reason: str | None

    events: list[DeliveryEventRead] = []
    created_at: datetime
    updated_at: datetime


class DeliveryQueueItemCancelBody(BaseModel):
    reason: str | None = None


class DeliveryQueueItemRetryBody(BaseModel):
    """Empty placeholder - retry_now() takes no input today (it forces an
    immediate send attempt using the item's existing content/attempt
    count). Kept as a typed body rather than omitted for the same
    forward-compat reason as DeliveryCampaignActionBody."""
