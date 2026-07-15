import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SearchTemplateBase(BaseModel):
    name: str
    description: str | None = None
    query_spec: dict[str, Any] = {}


class SearchTemplateCreate(SearchTemplateBase):
    pass


class SearchTemplateUpdate(SearchTemplateBase):
    name: str | None = None


class SearchTemplateRead(SearchTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID | None
    is_system_default: bool
    created_at: datetime
    updated_at: datetime
