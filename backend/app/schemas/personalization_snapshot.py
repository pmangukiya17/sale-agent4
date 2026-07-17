import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import BuyerReadinessLevel, RelationshipStage
from app.schemas.communication_strategy import CommunicationStrategyRead
from app.schemas.personalization_strategy import PersonalizationStrategyRead


class PersonalizationSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    version: int
    personalization_job_id: uuid.UUID | None
    company_profile_id: uuid.UUID
    is_current: bool

    buyer_persona: dict[str, Any] | None
    buyer_readiness: BuyerReadinessLevel
    buyer_readiness_reasoning: str | None
    relationship_stage_at_generation: RelationshipStage
    personalization_variables: dict[str, Any] | None

    communication_strategy: CommunicationStrategyRead | None
    strategies: list[PersonalizationStrategyRead] = []

    created_at: datetime
    updated_at: datetime
