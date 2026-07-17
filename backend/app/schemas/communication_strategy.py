import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import CommunicationFormality, CommunicationIntensityLevel, CommunicationLength


class CommunicationStrategyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    personalization_snapshot_id: uuid.UUID
    formality: CommunicationFormality
    directness: CommunicationIntensityLevel
    warmth: CommunicationIntensityLevel
    technical_depth: CommunicationIntensityLevel
    authority: CommunicationIntensityLevel
    consultative_level: CommunicationIntensityLevel
    urgency: CommunicationIntensityLevel
    message_length: CommunicationLength
    rationale: str | None
    created_at: datetime
