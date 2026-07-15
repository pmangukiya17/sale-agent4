import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DiscoveryRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    discovery_search_id: uuid.UUID
    discovery_job_id: uuid.UUID
    company_profile_id: uuid.UUID
    triggered_by_user_id: uuid.UUID | None
    triggered_at: datetime
    config_snapshot: dict[str, Any]
    prospects_found_count: int
    new_prospects_count: int
    duplicate_count: int
    created_at: datetime
