import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ProspectStatus
from app.schemas.prospect_contact import ProspectContactRead
from app.schemas.prospect_source import ProspectSourceRead


class ProspectUpdate(BaseModel):
    """Manual field overrides a reviewer can make - not a full replace,
    only what's provided is changed."""

    name: str | None = None
    website: str | None = None
    country: str | None = None
    industry_id: uuid.UUID | None = None
    buyer_type_id: uuid.UUID | None = None
    company_size_range: str | None = None
    description: str | None = None
    timezone: str | None = None


class ProspectRejectRequest(BaseModel):
    rejection_reason: str


class ProspectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    discovery_search_id: uuid.UUID | None
    name: str
    website: str | None
    country: str | None
    industry_id: uuid.UUID | None
    industry_raw: str | None
    buyer_type_id: uuid.UUID | None
    company_size_range: str | None
    description: str | None
    status: ProspectStatus
    total_score: float | None
    score_breakdown: list[dict[str, Any]] | None
    ai_reasoning: str | None
    first_discovered_at: datetime
    last_seen_at: datetime
    reviewed_by_user_id: uuid.UUID | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    potential_duplicate_of_prospect_id: uuid.UUID | None
    duplicate_confidence: float | None
    timezone: str | None
    contacts: list[ProspectContactRead] = []
    sources: list[ProspectSourceRead] = []
    created_at: datetime
    updated_at: datetime
