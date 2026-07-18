import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import DeliveryCampaignStatus


class DeliveryCampaignOverridesBase(BaseModel):
    """Every field here is an OPTIONAL override of the referenced
    SendingProfile's own defaults - null means "use the profile's
    default", exactly the fallback chain
    campaign_service._resolve_scheduling_config implements. Shared by
    Create and Update so the two can't drift out of sync on what's
    overridable."""

    sending_window_start: time | None = None
    sending_window_end: time | None = None
    min_gap_seconds: int | None = None
    max_gap_seconds: int | None = None
    hourly_limit: int | None = None
    daily_limit: int | None = None
    respect_recipient_timezone: bool = True
    # Forward-compat only - not read by FIFOSchedulingPolicy in M5. See
    # DeliveryCampaign's model docstring.
    priority: int = 0

    @field_validator("max_gap_seconds")
    @classmethod
    def _check_gap_order(cls, value: int | None, info) -> int | None:
        min_gap = info.data.get("min_gap_seconds")
        if value is not None and min_gap is not None and value < min_gap:
            raise ValueError("max_gap_seconds must be >= min_gap_seconds")
        return value


class DeliveryCampaignCreate(DeliveryCampaignOverridesBase):
    sending_profile_id: uuid.UUID
    name: str
    description: str | None = None
    # "500 approved drafts -> 500 queue items", frozen at creation time -
    # see campaign_service.create_campaign / DeliveryQueueItem's docstring.
    # Every id here must already be an OutreachDraftStatus.APPROVED,
    # is_current draft, or the whole create call fails (all-or-nothing,
    # no partial campaign left half-created from a bad id in the list).
    outreach_draft_ids: list[uuid.UUID]


class DeliveryCampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    sending_profile_id: uuid.UUID
    name: str
    description: str | None
    status: DeliveryCampaignStatus

    sending_window_start: time | None
    sending_window_end: time | None
    min_gap_seconds: int | None
    max_gap_seconds: int | None
    hourly_limit: int | None
    daily_limit: int | None
    respect_recipient_timezone: bool
    priority: int

    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DeliveryCampaignActionBody(BaseModel):
    """Empty placeholder body shared by the schedule/pause/resume actions
    - none of the three take input today (see campaign_service.py), but
    typing the route's body as this model rather than omitting it means a
    future field (e.g. a pause reason) is a field addition here, not a
    route signature change - same forward-compat convention
    OutreachRequestRunBody already established in M4."""


class DeliveryCampaignCancelBody(BaseModel):
    """Distinct from DeliveryCampaignActionBody (rather than reused) since
    Cancel is the one action where a reason is plausible future input,
    even though campaign_service.cancel_campaign doesn't accept one yet -
    it currently always logs reason="campaign_cancelled" on each queue
    item. Kept separate so adding that plumbing later doesn't reuse a
    generically-named body across unrelated actions."""

    reason: str | None = None


class AvailableOutreachDraftRead(BaseModel):
    """A denormalized, cross-prospect view of one APPROVED, is_current,
    not-actively-queued OutreachDraft - built specifically to power the
    Layer 6 campaign-creation picker (a business-wide "what can I put into
    a new campaign" list). Deliberately lives here, in delivery's own
    schema module, rather than in schemas/outreach_draft.py - the
    "exclude drafts with an active DeliveryQueueItem" filter behind this
    is delivery-specific knowledge, and putting the schema (and the route
    that fills it - see api/routes/delivery_campaigns.py) on delivery's
    side keeps the dependency one-way: Delivery reads Outreach, Outreach
    never has to know Delivery exists. Not built via from_attributes on a
    plain OutreachDraft - the route constructs this explicitly per row
    since prospect_name/contact_name/contact_email/subject_preview come
    from joined/nested data, not columns on OutreachDraft itself."""

    id: uuid.UUID
    channel_key: str
    version: int
    confidence: float | None
    prospect_id: uuid.UUID
    prospect_name: str
    prospect_contact_id: uuid.UUID
    contact_name: str | None
    contact_email: str | None
    subject_preview: str | None
