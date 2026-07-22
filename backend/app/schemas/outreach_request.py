import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import OutreachJobStatus
from app.schemas.outreach_playbook import OutreachPlaybookRead


class OutreachRequestBase(BaseModel):
    channel_key: str
    sequence_key: str | None = None
    sequence_position: int | None = None


class OutreachRequestCreate(OutreachRequestBase):
    # Playbook -> Request -> Job is a hard requirement, same mandatory
    # chain used since M1. prospect_id/prospect_contact_id come from the
    # URL path, not this body - same convention as ResearchRequestCreate.
    outreach_playbook_id: uuid.UUID


class OutreachRequestRead(OutreachRequestBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    prospect_contact_id: uuid.UUID
    company_profile_id: uuid.UUID
    outreach_playbook_id: uuid.UUID
    requested_by_user_id: uuid.UUID | None
    status: OutreachJobStatus
    outreach_playbook: OutreachPlaybookRead
    created_at: datetime
    updated_at: datetime


class OutreachRequestRunBody(BaseModel):
    """Placeholder body for the /run endpoint - Outreach has no per-run
    external input (same as Personalization's), kept for future use
    (e.g. a one-off tone override) without needing to change the route
    signature later."""
    notes: str | None = None


class OutreachRequestRunQueued(BaseModel):
    """M8.15: the /run endpoint's new response shape - mirrors
    PersonalizationRequestRunQueued/ResearchRequestRunQueued/
    DiscoverySearchRunQueued. No OutreachJob exists yet at the instant
    this response is sent; the frontend's Live Workflow Progress view
    finds the resulting job by polling
    GET .../outreach-jobs?outreach_request_id={request_id}."""

    status: str = "queued"
    outreach_request_id: uuid.UUID
