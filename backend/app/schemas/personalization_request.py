import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import PersonalizationJobStatus
from app.schemas.personalization_template import PersonalizationTemplateRead


class PersonalizationRequestBase(BaseModel):
    requested_focus_areas: list[str] | None = None


class PersonalizationRequestCreate(PersonalizationRequestBase):
    # Template -> Request -> Job is a hard requirement, same as Discovery's
    # and Research's chains. prospect_id comes from the URL path, not this
    # body - same convention as ResearchRequestCreate.
    personalization_template_id: uuid.UUID


class PersonalizationRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    company_profile_id: uuid.UUID
    personalization_template_id: uuid.UUID
    requested_by_user_id: uuid.UUID | None
    requested_focus_areas: list[str] | None
    status: PersonalizationJobStatus
    personalization_template: PersonalizationTemplateRead
    created_at: datetime
    updated_at: datetime


class PersonalizationRequestRunBody(BaseModel):
    """
    Personalization has no per-run external input (unlike Research's
    manual_document provider) - it only reads what's already stored. This
    body exists purely as a placeholder for future focus-area overrides at
    run time, kept optional and empty by default.
    """
    focus_areas: list[str] | None = None
