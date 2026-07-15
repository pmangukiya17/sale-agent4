import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ResearchReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    intelligence_snapshot_id: uuid.UUID
    research_job_id: uuid.UUID | None
    title: str
    summary: str | None
    content: dict[str, Any]
    generated_at: datetime
    generated_by: str
    created_at: datetime
