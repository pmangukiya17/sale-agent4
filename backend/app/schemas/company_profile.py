import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.timezones import validate_iana_timezone
from app.schemas.reference import IndustryRead


class CompanyProfileBase(BaseModel):
    name: str
    logo_url: str | None = None
    website: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    address: str | None = None
    about: str | None = None
    description: str | None = None
    business_type: list[str] | None = None
    production_capacity: str | None = None
    factory_location: str | None = None
    shipping_ports: list[str] | None = None
    export_certifications: list[str] | None = None
    minimum_order_quantity: str | None = None
    preferred_incoterms: list[str] | None = None
    preferred_payment_terms: list[str] | None = None
    timezone: str | None = None
    ai_instructions: str | None = None
    is_default: bool = False

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str | None) -> str | None:
        return validate_iana_timezone(value)


class CompanyProfileCreate(CompanyProfileBase):
    industry_ids: list[uuid.UUID] = []


class CompanyProfileUpdate(CompanyProfileBase):
    name: str | None = None
    industry_ids: list[uuid.UUID] | None = None


class CompanyProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    is_default: bool
    name: str
    logo_url: str | None
    website: str | None
    email: str | None
    phone: str | None
    country: str | None
    address: str | None
    about: str | None
    description: str | None
    business_type: list[str] | None
    production_capacity: str | None
    factory_location: str | None
    shipping_ports: list[str] | None
    export_certifications: list[str] | None
    minimum_order_quantity: str | None
    preferred_incoterms: list[str] | None
    preferred_payment_terms: list[str] | None
    timezone: str | None
    ai_instructions: str | None
    industries: list[IndustryRead] = []
    created_at: datetime
    updated_at: datetime
