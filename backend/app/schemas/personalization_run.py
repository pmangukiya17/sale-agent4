import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PersonalizationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    personalization_request_id: uuid.UUID
    personalization_job_id: uuid.UUID
    prospect_id: uuid.UUID
    company_profile_id: uuid.UUID
    triggered_by_user_id: uuid.UUID | None
    triggered_at: datetime
    config_snapshot: dict[str, Any]
    personalization_version_created: int | None
    created_at: datetime
