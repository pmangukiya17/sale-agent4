import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import PipelineStage


class CompanyBase(BaseModel):
    name: str
    country: str | None = None
    website_url: str | None = None
    industry: str | None = None
    notes: str | None = None


class CompanyCreate(CompanyBase):
    source: str | None = "manual"


class CompanyRead(CompanyBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str | None
    legitimacy_score: float | None
    icp_score: float | None
    stage: PipelineStage
    created_at: datetime
    updated_at: datetime
