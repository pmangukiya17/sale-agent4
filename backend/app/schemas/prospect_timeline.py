import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ProspectTimelineEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    event_type: str
    actor: str
    payload: dict[str, Any] | None
    created_at: datetime
