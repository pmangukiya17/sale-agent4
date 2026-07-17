import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import PersonalizationStrategyRank


class PersonalizationEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    personalization_strategy_id: uuid.UUID
    signal_id: uuid.UUID | None
    recommendation_id: uuid.UUID | None
    intelligence_snapshot_id: uuid.UUID | None
    excerpt: str | None


class PersonalizationStrategyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    personalization_snapshot_id: uuid.UUID
    strategy_rank: PersonalizationStrategyRank
    title: str
    narrative: str
    confidence: float | None
    reasoning: str | None
    evidence: list[PersonalizationEvidenceRead] = []
    created_at: datetime
