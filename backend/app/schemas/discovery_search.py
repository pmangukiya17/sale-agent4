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


class DiscoverySearchRunQueued(BaseModel):
    """M8.8: the /run endpoint's new response shape. Replaces the old
    synchronous DiscoveryJobRead return - no DiscoveryJob exists yet at
    the instant this response is sent (the trigger Event has only just
    been published; the Event Dispatcher and Step Runner workers create
    and execute it on their own next polling ticks - see
    app/api/routes/discovery_searches.py's run_search() docstring). The
    frontend's Live Workflow Progress view finds the resulting job by
    polling GET /company-profiles/{id}/discovery-jobs?discovery_search_id=
    {discovery_search_id} (already supports this filter, unchanged by
    M8.8) until one appears, then switches to watching that specific job."""

    status: str = "queued"
    discovery_search_id: uuid.UUID
