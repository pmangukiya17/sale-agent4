import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.raw_document import RawDocumentRead


class ResearchSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_job_id: uuid.UUID
    provider_key: str
    source_url: str | None
    source_identifier: str | None
    fetched_at: datetime | None
    status: str
    error_message: str | None
    raw_documents: list[RawDocumentRead] = []
    created_at: datetime
