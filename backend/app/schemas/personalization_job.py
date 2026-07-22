import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import PersonalizationJobStatus


class PersonalizationJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    personalization_request_id: uuid.UUID
    prospect_id: uuid.UUID
    company_profile_id: uuid.UUID
    status: PersonalizationJobStatus
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    log: list[dict[str, Any]]
    strategy_count: int
    created_at: datetime
    updated_at: datetime
