"""
The Real-Time stream's background poller - the one piece of this
platform that runs inside the FastAPI process itself rather than as a
separate worker container (see app/realtime/__init__.py's own docstring
for why that's a structural requirement here, not a style choice).

Deliberately POLLS `events` on a short interval
(REALTIME_STREAM_POLL_INTERVAL_SECONDS, default 1.5s) rather than using
Postgres LISTEN/NOTIFY - an explicit, approved M8.6 decision. Postgres
NOTIFY would genuinely be lower-latency, but it would also be a second
operational pattern in a platform where every other background
capability (event_dispatcher_worker, step_runner_worker, the delivery/
mailbox/thread-builder/reply-intelligence/notification workers) already
polls - and the approved call was that keeping one consistent,
already-understood operational model is worth more right now than
shaving a second or two of latency. NOTIFY remains a valid, disclosed
future upgrade if polling ever becomes a measurable bottleneck (see this
project's own "single-instance, sequential-loop simplification... additive
if this is ever scaled" precedent in event_dispatcher_worker.py's own
docstring for the same kind of forward-compatible, not-prematurely-
optimized reasoning).

Uses the SAME `sequence_no` total-order primitive every other consumer
of `events` already relies on - this poller tracks one global watermark
(the highest sequence_no it has already fanned out), queries strictly
past it each tick, and advances the watermark to whatever it just saw.
It does NOT replay history to new connections - a client's own catch-up
on (re)connect is handled separately, per-request, by
app/api/routes/realtime.py (querying `events` for that client's own
last-seen sequence_no, once, before subscribing to this poller's live
feed) - this poller only ever pushes what's NEW from the moment the
process started (or, more precisely, from the moment this module's
watermark was first initialized).

Everything here is synchronous, plain-SQLAlchemy DB access (SessionLocal,
same as every worker in this codebase) - deliberately run via
`asyncio.to_thread()` rather than called directly from the async tick
loop, since a blocking DB call executed directly on the single event loop
this process runs would stall every other concurrently-open SSE
connection (and every other concurrent request) for the duration of the
query. This is the first background asyncio task in this codebase
(every prior worker is synchronous and lives in its own OS process) -
called out explicitly since it's a new shape, not because it's exotic;
`asyncio.to_thread` is standard-library (Python 3.11, already this
project's floor).
"""
import asyncio
import logging

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.workflow_event import Event
from app.realtime.broadcaster import BROADCASTER
from app.schemas.event import EventRead

logger = logging.getLogger("sales_agent.realtime_poller")

_last_seen_sequence_no: int | None = None
_poll_task: asyncio.Task | None = None


def _fetch_new_events_sync(last_seen: int | None) -> list[Event]:
    """Runs on a worker thread via asyncio.to_thread - a fresh, short-
    lived session per tick, same discipline as every other worker's
    per-item session in this codebase (never one long-held session
    spanning the whole process lifetime).

    `last_seen is None` (no watermark established yet) is handled as its
    own case, fetching the NEWEST batch (DESC, then reversed back to
    ascending) rather than the plain `ORDER BY sequence_no ASC LIMIT n`
    every other tick uses. This was a real, latent bug (found + root-
    caused during CEO review, 2026-07-28 - see this project's own
    verify_m8_3_step6_gateway_diagnostics.sh for the full writeup):
    fetching the OLDEST batch with no floor works only as long as
    `events` holds fewer than REALTIME_STREAM_POLL_BATCH_SIZE rows total,
    system-wide - once a long-lived `events` table accumulates more
    history than that ahead of "now" (which any real, growing deployment
    eventually will), a event published the moment the watermark is
    unset would never fall inside that oldest-N window and would never
    be dispatched. In real production this branch is essentially never
    exercised - `_run_forever()` always calls `_initialize_watermark()`
    (MAX(sequence_no)) before the poll loop starts, so `last_seen` is
    only ever None here on a genuinely empty `events` table (where either
    ordering trivially returns nothing) - but this poller's own
    module docstring's contract ("push events published from the moment
    the watermark was established, not all of history") only holds if
    the None case means "catch me up starting now", not "start from the
    dawn of time"."""
    db = SessionLocal()
    try:
        if last_seen is None:
            stmt = select(Event).order_by(Event.sequence_no.desc()).limit(settings.REALTIME_STREAM_POLL_BATCH_SIZE)
            rows = list(db.scalars(stmt).all())
            rows.reverse()  # restore ascending order so the caller's watermark-advance loop stays monotonic
            return rows
        stmt = (
            select(Event)
            .where(Event.sequence_no > last_seen)
            .order_by(Event.sequence_no.asc())
            .limit(settings.REALTIME_STREAM_POLL_BATCH_SIZE)
        )
        return list(db.scalars(stmt).all())
    finally:
        db.close()


async def poll_once() -> int:
    """One tick: fetches events past the current watermark, fans each
    out to BROADCASTER for its own company_profile_id, advances the
    watermark. Returns how many events were dispatched this tick (0 is
    the overwhelmingly common case - most ticks find nothing new)."""
    global _last_seen_sequence_no

    new_events = await asyncio.to_thread(_fetch_new_events_sync, _last_seen_sequence_no)
    for event in new_events:
        payload = EventRead.model_validate(event).model_dump(mode="json")
        BROADCASTER.publish(event.company_profile_id, payload)
        _last_seen_sequence_no = event.sequence_no

    return len(new_events)


async def _initialize_watermark() -> None:
    """Sets the starting watermark to whatever the highest sequence_no
    already in `events` is at process startup, so this poller only ever
    pushes events published AFTER the backend came up - not the entire
    platform history to every future connection (that's the per-client
    reconnect-replay's job, in the route, not this poller's)."""
    global _last_seen_sequence_no

    def _max_sequence_no() -> int | None:
        db = SessionLocal()
        try:
            return db.scalar(select(Event.sequence_no).order_by(Event.sequence_no.desc()).limit(1))
        finally:
            db.close()

    _last_seen_sequence_no = await asyncio.to_thread(_max_sequence_no)


async def _run_forever() -> None:
    await _initialize_watermark()
    logger.info(
        "Realtime poller starting - poll_interval=%ss batch_size=%s starting_watermark=%s",
        settings.REALTIME_STREAM_POLL_INTERVAL_SECONDS,
        settings.REALTIME_STREAM_POLL_BATCH_SIZE,
        _last_seen_sequence_no,
    )
    while True:
        try:
            dispatched = await poll_once()
            if dispatched:
                logger.info("Realtime poller tick: dispatched %s event(s)", dispatched)
        except Exception:  # noqa: BLE001 - one bad tick must never kill the poller, same discipline as every worker loop
            logger.exception("Unhandled error in Realtime poller tick")
        await asyncio.sleep(settings.REALTIME_STREAM_POLL_INTERVAL_SECONDS)


def start() -> None:
    """Called once from app.main's own `lifespan`, at startup. Stores the
    task on this module so `stop()` can cancel it cleanly at shutdown -
    same "start/stop paired with the app's own lifecycle" shape as
    nothing else in this codebase needs, since every other background
    capability is an entirely separate process the ASGI app has no
    handle on."""
    global _poll_task
    _poll_task = asyncio.create_task(_run_forever())


async def stop() -> None:
    global _poll_task
    if _poll_task is None:
        return
    _poll_task.cancel()
    try:
        await _poll_task
    except asyncio.CancelledError:
        pass
    _poll_task = None
