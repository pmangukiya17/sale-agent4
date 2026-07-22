import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ResearchJobStatus
from app.schemas.research_template import ResearchTemplateRead


class ResearchRequestBase(BaseModel):
    requested_focus_areas: list[str] | None = None


class ResearchRequestCreate(ResearchRequestBase):
    # Template -> Request -> Job is a hard requirement, same as Discovery's
    # Search Template -> Search -> Job - every request must derive from a
    # template, there is no ad-hoc/templateless research request.
    # prospect_id is NOT part of this body - it comes from the URL path
    # (.../prospects/{prospect_id}/research-requests), the same way
    # DiscoverySearchCreate never repeats company_profile_id in its body.
    research_template_id: uuid.UUID


class ResearchRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    company_profile_id: uuid.UUID
    research_template_id: uuid.UUID
    requested_by_user_id: uuid.UUID | None
    requested_focus_areas: list[str] | None
    status: ResearchJobStatus
    research_template: ResearchTemplateRead
    created_at: datetime
    updated_at: datetime


class ResearchRequestRunBody(BaseModel):
    """
    Per-run input, merged on top of the ResearchTemplate's research_spec at
    execution time (never persisted on the ResearchRequest itself - see
    app/research/pipeline.py's module docstring for why). For the
    manual_document provider this is where the documents to analyze are
    supplied, e.g. {"documents": [{"document_type": "html_page",
    "extracted_text": "...", "source_url": "https://..."}]}.
    """
    source_types: list[str] | None = None
    documents: list[dict[str, Any]] | None = None


class ResearchRequestRunQueued(BaseModel):
    """M8.13: the /run endpoint's new response shape - exact mirror of
    DiscoverySearchRunQueued (app/schemas/discovery_search.py). No
    ResearchJob exists yet at the instant this response is sent; the
    frontend's Live Workflow Progress view finds the resulting job by
    polling GET .../research-jobs?research_request_id={request_id}."""

    status: str = "queued"
    research_request_id: uuid.UUID
