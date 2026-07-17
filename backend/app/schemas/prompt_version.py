import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PromptVersionBase(BaseModel):
    channel_key: str
    prompt_key: str
    prompt_text: str


class PromptVersionCreate(PromptVersionBase):
    # Creating a new PromptVersion always starts a fresh version for this
    # (company_profile_id, channel_key, prompt_key) lineage - append-only,
    # never edits a previous row. is_active defaults True at creation; the
    # route deactivates any prior active row for the same lineage.
    pass


class PromptVersionRead(PromptVersionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID | None
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
