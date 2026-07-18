"""
Randomized, human-like send-time generation within one sending window.
Pure and stdlib-only (no DB, no network) - deliberately, so it's testable
in complete isolation (see backend/tests/test_delivery_scheduler_windows.py)
and so campaign_service can call it repeatedly across multiple calendar
days without this module ever needing to know about campaigns, queue
items, or timezones. Timezone conversion happens one layer up (see
app.delivery.timezone.resolver.local_window_to_utc) - by the time a
window reaches this module it is already plain UTC datetimes, matching
"the provider layer should never know about timezone calculations" one
layer further down the stack: this module never touches ZoneInfo either.

daily_limit is NOT a parameter here - the caller (campaign_service) is
responsible for capping max_count at the remaining daily allowance before
calling this function once per calendar day. hourly_limit IS handled here
because it's a rolling-window constraint *within* a single window call,
not something the caller can easily pre-slice.
"""
import random
from datetime import datetime, timedelta


def generate_send_times(
    window_start: datetime,
    window_end: datetime,
    max_count: int,
    min_gap_seconds: int,
    max_gap_seconds: int,
    hourly_limit: int | None = None,
    rng: random.Random | None = None,
) -> list[datetime]:
    """Generates up to max_count monotonically increasing timestamps in
    [window_start, window_end), each gap after the first drawn uniformly
    from [min_gap_seconds, max_gap_seconds] - e.g. 08:01, 08:05, 08:11,
    08:17, 08:24, 08:31, never a fixed interval. Stops early (returns
    fewer than max_count) if the window or hourly_limit doesn't allow
    fitting them all; the caller schedules the remainder in a later
    window (the next calendar day).

    Raises ValueError for nonsensical input (min_gap > max_gap, negative
    gaps, non-positive max_count) rather than silently producing a
    misleading result.
    """
    if max_count <= 0:
        return []
    if min_gap_seconds < 0 or max_gap_seconds < 0:
        raise ValueError("gap seconds must be non-negative")
    if min_gap_seconds > max_gap_seconds:
        raise ValueError("min_gap_seconds must be <= max_gap_seconds")
    if window_end <= window_start:
        return []

    rng = rng or random.Random()
    times: list[datetime] = []
    hour_bucket_start = window_start
    count_in_bucket = 0

    candidate = window_start
    while len(times) < max_count:
        if hourly_limit is not None and count_in_bucket >= hourly_limit:
            # This hour is full - jump straight to the next rolling-hour
            # boundary rather than keep drawing gaps that will just get
            # rejected one at a time.
            hour_bucket_start = hour_bucket_start + timedelta(hours=1)
            candidate = hour_bucket_start
            count_in_bucket = 0

        if candidate >= window_end:
            break

        if candidate - hour_bucket_start >= timedelta(hours=1):
            hour_bucket_start = candidate
            count_in_bucket = 0

        times.append(candidate)
        count_in_bucket += 1

        gap = rng.uniform(min_gap_seconds, max_gap_seconds)
        candidate = candidate + timedelta(seconds=gap)

    return times
