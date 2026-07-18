import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import DeliveryEventType


class DeliveryEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    delivery_queue_item_id: uuid.UUID
    event_type: DeliveryEventType
    occurred_at: datetime
    detail: dict[str, Any] | None
