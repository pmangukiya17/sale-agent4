"""
M8.6 Real-Time Event Streaming - the HTTP surface over app/realtime/'s
in-process broadcaster+poller. Two endpoints, deliberately using two
DIFFERENT auth mechanisms for the reason explained in
app/realtime/tickets.py's own docstring:

  - POST /company-profiles/{id}/event-stream/ticket - normal
    Authorization: Bearer auth (get_owned_company_profile, same
    ownership-scoping dependency every other company-scoped route in
    this codebase already uses). Mints a short-lived stream ticket for
    exactly this company_profile_id.

  - GET /company-profiles/{id}/event-stream - the actual SSE connection.
    Cannot use the Authorization header at all (see tickets.py) -
    authenticates via the `ticket` query parameter minted by the
    endpoint above instead, verified by _get_company_profile_via_ticket()
    below (a parallel, ticket-based equivalent of
    get_owned_company_profile - same 404-not-403 ownership-hiding
    behavior, same "profile must belong to this caller" guarantee, just
    sourced from a different credential).

Deliberately named "event-stream" (one word-with-hyphen segment), NOT
nested under the existing "events" path prefix as "/events/stream" -
app/api/routes/events.py already registers
GET /company-profiles/{id}/events/{event_id} with event_id as a plain,
untyped path parameter. Starlette compiles an untyped path parameter to
match ANY non-slash segment at the routing layer - type validation
(rejecting "stream" as not a valid UUID) happens later, inside FastAPI's
own dependency resolution, AFTER a route has already been matched purely
on path shape. So "/events/stream" would collide with "/events/{event_id}"
at the routing layer, and which one actually wins would depend entirely
on which router happened to be include_router()'d first in app/main.py -
a fragile, easy-to-silently-break-later ordering dependency. Using a
distinct path segment ("event-stream") sidesteps the collision by
construction, with no dependency on router registration order at all.

Read-only from the platform's perspective in the same sense
app/api/routes/events.py is: this router never constructs an Event or a
Notification, and never writes anything - it only ever reads `events`
(via app.realtime.poller's already-running background task) and fans
rows out to whichever connections are open.
"""
import asyncio
import json
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models.company_profile import CompanyProfile
from app.models.workflow_event import Event
from app.realtime.broadcaster import BROADCASTER
from app.realtime.tickets import create_stream_ticket, verify_stream_ticket
from app.schemas.event import EventRead
from app.schemas.realtime import StreamTicketRead

router = APIRouter()

# How often a keep-alive SSE comment is sent on an otherwise-idle
# connection - not a business setting (nothing about how often real
# Events arrive), just enough to keep intermediary proxies/load balancers
# from timing out a connection that looks inactive at the TCP level.
_KEEPALIVE_INTERVAL_SECONDS = 20.0


@router.post(
    "/company-profiles/{company_profile_id}/event-stream/ticket",
    response_model=StreamTicketRead,
)
def create_ticket(
    profile: CompanyProfile = Depends(get_owned_company_profile),
) -> StreamTicketRead:
    ticket = create_stream_ticket(user_id=profile.owner_user_id, company_profile_id=profile.id)
    return StreamTicketRead(ticket=ticket, expires_in_seconds=settings.REALTIME_STREAM_TICKET_EXPIRE_SECONDS)


def _get_company_profile_via_ticket(
    company_profile_id: uuid.UUID,
    ticket: str = Query(...),
    db: Session = Depends(get_db),
) -> CompanyProfile:
    """Ticket-based equivalent of get_owned_company_profile - see this
    module's own docstring for why the SSE endpoint can't use the normal
    Bearer dependency. Returns 404 (never 403) for every failure mode -
    expired/malformed/wrong-purpose ticket, ticket minted for a
    DIFFERENT company_profile_id than the one in this URL, or a profile
    that genuinely doesn't belong to the ticket's own user - same
    "don't leak which case it was" discipline get_owned_company_profile
    itself documents.
    """
    credentials_exception = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company profile not found")

    decoded = verify_stream_ticket(ticket)
    if decoded is None:
        raise credentials_exception
    ticket_user_id, ticket_company_profile_id = decoded

    if ticket_company_profile_id != company_profile_id:
        raise credentials_exception

    profile = db.get(CompanyProfile, company_profile_id)
    if profile is None or profile.owner_user_id != ticket_user_id:
        raise credentials_exception

    return profile


def _fetch_backlog_sync(db: Session, company_profile_id: uuid.UUID, since_sequence: int) -> list[Event]:
    stmt = (
        select(Event)
        .where(Event.company_profile_id == company_profile_id, Event.sequence_no > since_sequence)
        .order_by(Event.sequence_no.asc())
        .limit(settings.REALTIME_STREAM_POLL_BATCH_SIZE)
    )
    return list(db.scalars(stmt).all())


def _format_sse(payload: dict) -> str:
    # `id:` carries sequence_no so a native EventSource's Last-Event-ID
    # would work if this connection is ever driven by native reconnect -
    # see useEventStream.ts's own docstring for why the frontend
    # deliberately does NOT rely on that today (short-lived query-param
    # tickets don't survive a native reconnect to the same URL), but
    # setting `id:` correctly anyway costs nothing and keeps the door
    # open for a future generic SSE client that does use it.
    return f"id: {payload['sequence_no']}\ndata: {json.dumps(payload)}\n\n"


async def _stream_events(company_profile_id: uuid.UUID, since_sequence: int | None) -> AsyncIterator[str]:
    queue = BROADCASTER.subscribe(company_profile_id)
    try:
        if since_sequence is not None:
            def _run_backlog_query() -> list[Event]:
                # A fresh, short-lived session for this one backlog
                # query only - constructed directly (not via the get_db
                # FastAPI dependency, which is a generator meant to be
                # driven by FastAPI's own DI, not called manually here).
                db = SessionLocal()
                try:
                    return _fetch_backlog_sync(db, company_profile_id, since_sequence)
                finally:
                    db.close()

            backlog = await asyncio.to_thread(_run_backlog_query)
            for event in backlog:
                yield _format_sse(EventRead.model_validate(event).model_dump(mode="json"))

        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield _format_sse(payload)
    finally:
        # Always reached - normal client disconnect (GeneratorExit) and
        # any unexpected error alike - so a dropped connection never
        # leaks a queue in BROADCASTER forever.
        BROADCASTER.unsubscribe(company_profile_id, queue)


@router.get("/company-profiles/{company_profile_id}/event-stream")
async def stream_events(
    since_sequence: int | None = Query(None, description="Replay Events with sequence_no greater than this before switching to live tailing - the reconnect/catch-up mechanism."),
    profile: CompanyProfile = Depends(_get_company_profile_via_ticket),
) -> StreamingResponse:
    return StreamingResponse(
        _stream_events(profile.id, since_sequence),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Common nginx-specific hint to disable proxy buffering for
            # this response - harmless when nothing in front of this
            # backend is nginx, load-bearing the day something is.
            "X-Accel-Buffering": "no",
        },
    )
