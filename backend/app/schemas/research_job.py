import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ResearchJobStatus
from app.schemas.ai_analysis import AIAnalysisRead
from app.schemas.research_source import ResearchSourceRead


class ResearchJobProviderRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_job_id: uuid.UUID
    provider_key: str
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    request_count: int
    api_cost: float | None
    token_usage: int | None
    status: str
    error_message: str | None


class ResearchJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_request_id: uuid.UUID
    prospect_id: uuid.UUID
    company_profile_id: uuid.UUID
    status: ResearchJobStatus
    started_at: datetime | None
    finished_at: datetime | None
    sources_used: list[str]
    raw_document_count: int
    signal_count: int
    recommendation_count: int
    error_message: str | None
    log: list[dict[str, Any]]
    provider_runs: list[ResearchJobProviderRunRead] = []
    # Unlike DiscoveryJob, ResearchJob nests its evidence trail directly -
    # "Evidence" is an explicit required frontend page for M2 (Research
    # Sources / Raw Documents / AI Analyses), where M1 never required a
    # user-facing view of DiscoveryProviderResult.
    sources: list[ResearchSourceRead] = []
    analyses: list[AIAnalysisRead] = []
    created_at: datetime
    updated_at: datetime
