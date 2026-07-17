import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PersonalizationTemplateBase(BaseModel):
    name: str
    description: str | None = None
    personalization_spec: dict[str, Any] = {}


class PersonalizationTemplateCreate(PersonalizationTemplateBase):
    pass


class PersonalizationTemplateUpdate(PersonalizationTemplateBase):
    name: str | None = None


class PersonalizationTemplateRead(PersonalizationTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID | None
    is_system_default: bool
    created_at: datetime
    updated_at: datetime
