import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.discovery.scoring import SCORING_FACTOR_NAMES
from app.models.enums import SearchDepth, SearchFrequency
from app.schemas.reference import BuyerTypeRead, CountryRead, IndustryRead, LanguageRead


class ICPCriteriaBase(BaseModel):
    name: str
    weight: float = 1.0
    is_active: bool = False
    preferred_company_size: list[str] | None = None
    minimum_confidence_score: float | None = None
    exclude_duplicate_companies: bool = True
    search_depth: SearchDepth = SearchDepth.STANDARD
    search_frequency: SearchFrequency = SearchFrequency.MANUAL
    rules: dict[str, Any] = {}
    # M2 Phase 1b: a schema-only convenience field over
    # rules["scoring_weights"] (ICPCriteria has no such mapped column -
    # per the CEO's explicit direction to reuse the existing JSONB escape
    # hatch rather than add one). On Create/Update this is an optional,
    # partial override - any factor not named here keeps the platform
    # default. None (the default) means "use platform defaults for every
    # factor". See app.discovery.scoring.DEFAULT_WEIGHTS/resolve_weights.
    scoring_weights: dict[str, float] | None = None

    @field_validator("scoring_weights")
    @classmethod
    def _check_scoring_weights(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is None:
            return None
        unknown = set(value) - SCORING_FACTOR_NAMES
        if unknown:
            raise ValueError(
                f"Unknown scoring factor(s): {sorted(unknown)}. Valid factors: {sorted(SCORING_FACTOR_NAMES)}"
            )
        total = sum(value.values())
        if abs(total - 100) > 0.01:
            raise ValueError(f"scoring_weights must sum to 100, got {total}")
        return value


class ICPCriteriaCreate(ICPCriteriaBase):
    target_buyer_type_ids: list[uuid.UUID] = []
    target_market_country_ids: list[uuid.UUID] = []
    excluded_country_ids: list[uuid.UUID] = []
    language_ids: list[uuid.UUID] = []
    target_industry_ids: list[uuid.UUID] = []


class ICPCriteriaUpdate(ICPCriteriaBase):
    name: str | None = None
    target_buyer_type_ids: list[uuid.UUID] | None = None
    target_market_country_ids: list[uuid.UUID] | None = None
    excluded_country_ids: list[uuid.UUID] | None = None
    language_ids: list[uuid.UUID] | None = None
    target_industry_ids: list[uuid.UUID] | None = None


class ICPCriteriaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    version: int
    name: str
    weight: float
    is_active: bool
    preferred_company_size: list[str] | None
    minimum_confidence_score: float | None
    exclude_duplicate_companies: bool
    search_depth: SearchDepth
    search_frequency: SearchFrequency
    rules: dict[str, Any]
    # Always the complete, default-filled effective weights (read from
    # the ICPCriteria.scoring_weights @property, never a partial dict) -
    # see that property's own docstring.
    scoring_weights: dict[str, float]
    target_buyer_types: list[BuyerTypeRead] = []
    target_markets: list[CountryRead] = []
    excluded_countries: list[CountryRead] = []
    languages: list[LanguageRead] = []
    target_industries: list[IndustryRead] = []
    created_at: datetime
    updated_at: datetime
