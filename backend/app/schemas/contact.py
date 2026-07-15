import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ContactBase(BaseModel):
    name: str | None = None
    role: str | None = None
    email: str | None = None
    phone: str | None = None


class ContactCreate(ContactBase):
    company_id: uuid.UUID
    source: str | None = "manual"


class ContactRead(ContactBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    source: str | None
    confidence_score: float | None
    created_at: datetime
    updated_at: datetime
