"""
Shared IANA timezone validation, used by any schema with a `timezone` field
(CompanyProfile, WorkspaceSettings, and later Company/Contact once those
are exposed via the API). Uses the stdlib tz database - no extra dependency.
"""
from zoneinfo import available_timezones

_VALID_TIMEZONES = available_timezones()


def validate_iana_timezone(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in _VALID_TIMEZONES:
        raise ValueError(f"'{value}' is not a recognized IANA timezone (e.g. 'Europe/Berlin').")
    return value
