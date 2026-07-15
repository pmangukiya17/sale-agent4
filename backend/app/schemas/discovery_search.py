import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import SearchDepth, SearchFrequency
from app.schemas.search_template import SearchTemplateRead


class DiscoverySearchBase(BaseModel):
    name: str
    query_spec: dict[str, Any] = {}
    provider_keys: list[str] = []
    search_depth: SearchDepth = SearchDepth.STANDARD
    search_frequency: SearchFrequency = SearchFrequency.MANUAL
    is_active: bool = True


class DiscoverySearchCreate(DiscoverySearchBase):
    # Search Template -> Search -> Job is a hard requirement - every search
    # must derive from a template, there is no ad-hoc/templateless search.
    search_template_id: uuid.UUID
    icp_criteria_id: uuid.UUID | None = None


class DiscoverySearchUpdate(DiscoverySearchBase):
    name: str | None = None
    search_template_id: uuid.UUID | None = None
    icp_criteria_id: uuid.UUID | None = None


class DiscoverySearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    search_template_id: uuid.UUID
    icp_criteria_id: uuid.UUID | None
    name: str
    query_spec: dict[str, Any]
    provider_keys: list[str]
    search_depth: SearchDepth
    search_frequency: SearchFrequency
    is_active: bool
    search_template: SearchTemplateRead
    created_at: datetime
    updated_at: datetime
