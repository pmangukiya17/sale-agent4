import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProspectSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    provider_key: str
    source_url: str | None
    discovered_at: datetime
    provider_confidence: float | None
    raw_result_id: uuid.UUID | None
    created_at: datetime
