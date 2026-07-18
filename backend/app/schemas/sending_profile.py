import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.timezones import validate_iana_timezone


class SendingProfileBase(BaseModel):
    """provider_key is a plain string, not a validated enum choice, for
    the same reason channel_key/DiscoveryProvider.key are - it's a
    pluggable-registry key (see app/delivery/providers/registry.py), so
    adding a provider is a code change, never a schema/migration change.
    The service layer (get_provider) is what rejects an unknown key, the
    same division of responsibility OutreachRequestCreate.channel_key
    already uses."""

    provider_key: str
    label: str
    sender_name: str
    sender_email: str
    reply_to_email: str | None = None
    is_active: bool = True

    daily_limit: int | None = None
    hourly_limit: int | None = None
    min_gap_seconds: int | None = None
    max_gap_seconds: int | None = None

    sending_window_start: time | None = None
    sending_window_end: time | None = None
    sending_timezone: str | None = None
    sending_days: list[str] | None = None

    @field_validator("sending_timezone")
    @classmethod
    def _check_sending_timezone(cls, value: str | None) -> str | None:
        return validate_iana_timezone(value)

    @field_validator("max_gap_seconds")
    @classmethod
    def _check_gap_order(cls, value: int | None, info) -> int | None:
        min_gap = info.data.get("min_gap_seconds")
        if value is not None and min_gap is not None and value < min_gap:
            raise ValueError("max_gap_seconds must be >= min_gap_seconds")
        return value


class SendingProfileCreate(SendingProfileBase):
    # A profile can be created before any mailbox is connected (see the
    # model's docstring) - this is intentionally optional, set later via
    # the Connect/Reconnect OAuth flow, never required up front.
    provider_connection_id: uuid.UUID | None = None


class SendingProfileUpdate(BaseModel):
    """Every field optional - a PATCH-style partial update, same
    convention as CompanyProfileUpdate. provider_key is deliberately NOT
    updatable here: changing which provider a profile targets is a
    reconnect operation (a new/different ProviderConnection), not a plain
    field edit - see connection_service.py."""

    label: str | None = None
    sender_name: str | None = None
    sender_email: str | None = None
    reply_to_email: str | None = None
    is_active: bool | None = None
    provider_connection_id: uuid.UUID | None = None

    daily_limit: int | None = None
    hourly_limit: int | None = None
    min_gap_seconds: int | None = None
    max_gap_seconds: int | None = None

    sending_window_start: time | None = None
    sending_window_end: time | None = None
    sending_timezone: str | None = None
    sending_days: list[str] | None = None

    @field_validator("sending_timezone")
    @classmethod
    def _check_sending_timezone(cls, value: str | None) -> str | None:
        return validate_iana_timezone(value)


class SendingProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    provider_connection_id: uuid.UUID | None
    provider_key: str
    label: str
    sender_name: str
    sender_email: str
    reply_to_email: str | None
    is_active: bool

    daily_limit: int | None
    hourly_limit: int | None
    min_gap_seconds: int | None
    max_gap_seconds: int | None

    sending_window_start: time | None
    sending_window_end: time | None
    sending_timezone: str | None
    sending_days: list[str] | None
    created_at: datetime
    updated_at: datetime
