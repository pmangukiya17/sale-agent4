import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import DecisionMakerLevel


class ProspectContactBase(BaseModel):
    name: str | None = None
    role: str | None = None
    department: str | None = None
    decision_maker_level: DecisionMakerLevel = DecisionMakerLevel.UNKNOWN
    email: str | None = None
    phone: str | None = None
    source: str | None = None
    confidence: float | None = None
    timezone: str | None = None
    working_hours: dict | None = None
    preferred_contact_time: dict | None = None


class ProspectContactCreate(ProspectContactBase):
    pass


class ProspectContactUpdate(ProspectContactBase):
    pass


class ProspectContactRead(ProspectContactBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
