import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import SearchDepth, SearchFrequency
from app.schemas.reference import BuyerTypeRead, CountryRead, LanguageRead


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


class ICPCriteriaCreate(ICPCriteriaBase):
    target_buyer_type_ids: list[uuid.UUID] = []
    target_market_country_ids: list[uuid.UUID] = []
    excluded_country_ids: list[uuid.UUID] = []
    language_ids: list[uuid.UUID] = []


class ICPCriteriaUpdate(ICPCriteriaBase):
    name: str | None = None
    target_buyer_type_ids: list[uuid.UUID] | None = None
    target_market_country_ids: list[uuid.UUID] | None = None
    excluded_country_ids: list[uuid.UUID] | None = None
    language_ids: list[uuid.UUID] | None = None


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
    target_buyer_types: list[BuyerTypeRead] = []
    target_markets: list[CountryRead] = []
    excluded_countries: list[CountryRead] = []
    languages: list[LanguageRead] = []
    created_at: datetime
    updated_at: datetime
