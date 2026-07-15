import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RawDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_source_id: uuid.UUID
    prospect_id: uuid.UUID
    document_type: str
    raw_html: str | None
    raw_json: dict[str, Any] | None
    extracted_text: str | None
    doc_metadata: dict[str, Any] | None
    fetched_at: datetime | None
    content_hash: str | None
    created_at: datetime
