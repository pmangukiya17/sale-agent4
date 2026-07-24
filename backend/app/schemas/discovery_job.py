import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import DiscoveryJobStatus


class DiscoveryJobCancelRequest(BaseModel):
    """M2 Phase 1c. `reason` is optional and, since DiscoveryJob has no
    dedicated cancelled_reason column (this phase reuses the existing
    job.log JSONB list instead of adding one - see the migration's own
    docstring for why), it is recorded as a job.log entry by the cancel
    route, not as a new mapped field anywhere."""

    reason: str | None = None


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
    # M2 Phase 1c - a REQUEST, distinct from status; see DiscoveryJob's
    # own model docstring/migration for why cancellation isn't modeled
    # as an immediate status write from this schema's own route.
    cancel_requested_at: datetime | None
    cancel_requested_by_user_id: uuid.UUID | None
    provider_runs: list[DiscoveryJobProviderRunRead] = []
    created_at: datetime
    updated_at: datetime
