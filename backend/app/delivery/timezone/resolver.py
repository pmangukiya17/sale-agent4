"""
Recipient timezone resolution. Prospect/ProspectContact.timezone are IANA
strings but almost always null in practice - nothing before M5 ever
populates them (see their model docstrings). This module is the actual
fallback chain: explicit value on the contact/prospect, else the
resolved Country.default_timezone, else UTC. Pure, stdlib-only (zoneinfo),
no DB/network access - the DB read of country.default_timezone happens in
the calling service; this module only validates and chooses between
already-fetched strings, which is what makes it independently unit-
testable without a database.

The provider layer never calls this - by design, per the M5 brief
("provider layer should never know about timezone calculations"). Only
the scheduler does, when respect_recipient_timezone is set on a
DeliveryCampaign.
"""
from datetime import date, datetime, time, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC_FALLBACK = "UTC"


def is_valid_iana_timezone(tz_name: str | None) -> bool:
    if not tz_name:
        return False
    try:
        ZoneInfo(tz_name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def resolve_recipient_timezone(
    explicit_timezone: str | None,
    country_default_timezone: str | None,
) -> str:
    """explicit_timezone (ProspectContact.timezone, falling back to
    Prospect.timezone - the caller decides which to pass, contact first)
    wins if it's a valid IANA zone. Otherwise country_default_timezone
    (Country.default_timezone for the prospect's country, added in
    migration 0008) if valid. Otherwise UTC - always returns *something*
    usable, never None, so callers never need a null-check.
    """
    for candidate in (explicit_timezone, country_default_timezone):
        if is_valid_iana_timezone(candidate):
            return candidate
    return UTC_FALLBACK


def local_window_to_utc(
    local_date: date,
    window_start: time,
    window_end: time,
    tz_name: str,
) -> tuple[datetime, datetime]:
    """Converts a local business-hours window on one calendar date into
    the UTC instants it corresponds to, so scheduler/windows.py (which
    only ever deals in UTC datetimes) never has to touch a ZoneInfo
    itself. Falls back to UTC if tz_name somehow isn't valid at call time
    (defensive - resolve_recipient_timezone above should already guarantee
    a valid zone, but this function doesn't trust that blindly)."""
    zone = ZoneInfo(tz_name) if is_valid_iana_timezone(tz_name) else dt_timezone.utc
    start_local = datetime.combine(local_date, window_start, tzinfo=zone)
    end_local = datetime.combine(local_date, window_end, tzinfo=zone)
    return start_local.astimezone(dt_timezone.utc), end_local.astimezone(dt_timezone.utc)
