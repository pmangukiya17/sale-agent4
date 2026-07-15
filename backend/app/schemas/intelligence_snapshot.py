import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.recommendation import RecommendationRead
from app.schemas.signal import SignalRead


class IntelligenceSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    version: int
    research_job_id: uuid.UUID | None
    company_profile_id: uuid.UUID
    is_current: bool

    business_model: str | None
    products_offered: list | None
    markets_served: list | None
    certifications: list | None
    manufacturing_or_trading: str | None
    sustainability_notes: str | None
    import_export_activity: list | None

    buyer_notes: str | None
    procurement_structure: str | None
    purchasing_process: str | None

    signals_summary: str | None

    signals: list[SignalRead] = []
    recommendations: list[RecommendationRead] = []

    created_at: datetime
    updated_at: datetime
