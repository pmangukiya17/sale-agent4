import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ResearchTemplateBase(BaseModel):
    name: str
    description: str | None = None
    research_spec: dict[str, Any] = {}


class ResearchTemplateCreate(ResearchTemplateBase):
    pass


class ResearchTemplateUpdate(ResearchTemplateBase):
    name: str | None = None


class ResearchTemplateRead(ResearchTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID | None
    is_system_default: bool
    created_at: datetime
    updated_at: datetime
