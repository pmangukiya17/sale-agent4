import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import TaskPriority, TaskStatus


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    prospect_id: uuid.UUID
    prospect_contact_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    assigned_user_id: uuid.UUID | None
    suggested_action: str
    source_event_type: str
    priority: TaskPriority
    status: TaskStatus
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
