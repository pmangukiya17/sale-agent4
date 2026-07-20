import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import DiscoveryJobStatus


class DiscoveryJobProviderRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    discovery_job_id: uuid.UUID
    provider_key: str
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    request_count: int
    api_cost: float | None
    token_usage: int | None
    status: str
    error_message: str | None


class DiscoveryJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    discovery_search_id: uuid.UUID
    company_profile_id: uuid.UUID
    status: DiscoveryJobStatus
    started_at: datetime | None
    finished_at: datetime | None
    providers_used: list[str]
    raw_result_count: int
    prospect_created_count: int
    prospect_matched_count: int
    prospect_qualified_count: int
    prospect_rejected_count: int
    error_message: str | None
    log: list[dict[str, Any]]
    provider_runs: list[DiscoveryJobProviderRunRead] = []
    created_at: datetime
    updated_at: datetime
