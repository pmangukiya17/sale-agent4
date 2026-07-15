import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.timezones import validate_iana_timezone
from app.models.enums import DateFormat, TimeFormat
from app.schemas.reference import CurrencyRead, LanguageRead


class WorkspaceSettingsBase(BaseModel):
    default_timezone: str | None = None
    default_language_id: uuid.UUID | None = None
    default_currency_id: uuid.UUID | None = None
    date_format: DateFormat = DateFormat.YYYY_MM_DD
    time_format: TimeFormat = TimeFormat.H24

    @field_validator("default_timezone")
    @classmethod
    def _check_timezone(cls, value: str | None) -> str | None:
        return validate_iana_timezone(value)


class WorkspaceSettingsUpdate(WorkspaceSettingsBase):
    pass


class WorkspaceSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    default_timezone: str | None
    date_format: DateFormat
    time_format: TimeFormat
    default_language: LanguageRead | None
    default_currency: CurrencyRead | None
    created_at: datetime
    updated_at: datetime
