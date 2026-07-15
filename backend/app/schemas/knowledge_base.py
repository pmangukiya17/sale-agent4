import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KnowledgeBaseBase(BaseModel):
    title: str
    content: str
    tags: list[str] | None = None
    category: str | None = None


class KnowledgeBaseCreate(KnowledgeBaseBase):
    pass


class KnowledgeBaseUpdate(KnowledgeBaseBase):
    title: str | None = None
    content: str | None = None


class KnowledgeBaseRead(KnowledgeBaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
