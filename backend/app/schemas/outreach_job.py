import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import OutreachJobStatus


class OutreachJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outreach_request_id: uuid.UUID
    prospect_id: uuid.UUID
    prospect_contact_id: uuid.UUID
    company_profile_id: uuid.UUID
    personalization_snapshot_id: uuid.UUID | None
    prompt_version_id: uuid.UUID | None
    status: OutreachJobStatus
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    log: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
