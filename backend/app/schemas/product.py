import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ProductStatus


class ProductBase(BaseModel):
    name: str
    category: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    hs_code: str | None = None
    image_urls: list[str] | None = None
    status: ProductStatus = ProductStatus.ACTIVE
    applications: list[str] | None = None
    specifications: dict[str, Any] | None = None
    packaging: str | None = None
    moq: str | None = None
    lead_time: str | None = None
    production_capacity: str | None = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductBase):
    name: str | None = None
    status: ProductStatus | None = None


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
