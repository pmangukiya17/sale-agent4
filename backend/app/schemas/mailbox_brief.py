import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MailboxBriefRecommendationRead(BaseModel):
    title: str
    rationale: str
    source_type: str | None = None
    source_id: str | None = None


class MailboxBriefRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    generated_at: datetime
    ai_provider: str
    ai_model: str
    summary: str
    recommendations: list[MailboxBriefRecommendationRead]
    statistics: dict[str, Any]
    requested_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
