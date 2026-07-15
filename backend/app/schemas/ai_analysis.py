import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import AIAnalysisType


class AIAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_job_id: uuid.UUID
    prospect_id: uuid.UUID
    analysis_type: AIAnalysisType
    model_used: str
    prompt_version: str
    raw_model_output: dict[str, Any] | None
    structured_output: dict[str, Any]
    confidence: float | None
    reasoning: str | None
    token_usage: int | None
    api_cost: float | None
    created_at: datetime
