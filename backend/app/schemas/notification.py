import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    event_id: uuid.UUID
    user_id: uuid.UUID | None
    title: str
    message: str
    priority: str
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class NotificationMarkAllReadResult(BaseModel):
    """Response for the bulk mark-all-read action - how many rows were
    actually flipped, so the frontend can show real feedback ("12 marked
    read") rather than assuming success silently changed something."""

    marked_count: int
