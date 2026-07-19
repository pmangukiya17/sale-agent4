"""
Stream tickets - a short-lived, narrowly-scoped credential for exactly
one thing: opening GET /company-profiles/{id}/events/stream. Every other
endpoint in this platform authenticates via the normal
`Authorization: Bearer <access_token>` header (see app.api.deps.
get_current_user / app.core.security.create_access_token) - that stays
completely unchanged. This module exists only because the browser's
native EventSource API cannot attach a custom Authorization header at
all, so the one connection that needs to travel as plain HTTP GET has to
carry its credential somewhere else - a query parameter is the
conventional, and only practical, place.

Deliberately a SEPARATE encode/decode pair from create_access_token/
decode_access_token in app.core.security, not a reuse of them, for two
reasons: (1) a stream ticket is scoped to one specific
company_profile_id (the normal access token is not - ownership is
re-checked per request via get_owned_company_profile instead), and (2)
the `purpose` claim below means a stream ticket can never be replayed as
a normal API bearer token, and a normal access token can never be used
to open a stream - two structurally different credentials, even though
both happen to be signed with the same SECRET_KEY/ALGORITHM. Still reuses
those two settings directly (rather than inventing a second secret) since
this is the same trust boundary (this backend, this deployment) - just a
narrower-scoped credential within it.

Short-lived (REALTIME_STREAM_TICKET_EXPIRE_SECONDS, default 300s) since
it only ever needs to be valid for the moment between minting (POST
/realtime/tickets, normal Bearer auth) and the SSE connection actually
opening. If a long-lived connection later drops and needs to reconnect
after the ticket has expired, the frontend mints a fresh one first - see
frontend/src/realtime/useEventStream.ts's own reconnect handling, which
does NOT rely on EventSource's native auto-reconnect for exactly this
reason (native auto-reconnect would retry the same, now-stale, ticket
embedded in the original URL forever).
"""
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import settings

_TICKET_PURPOSE = "realtime_stream"


def create_stream_ticket(*, user_id: uuid.UUID, company_profile_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(seconds=settings.REALTIME_STREAM_TICKET_EXPIRE_SECONDS)
    payload = {
        "sub": str(user_id),
        "company_profile_id": str(company_profile_id),
        "purpose": _TICKET_PURPOSE,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_stream_ticket(ticket: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Returns (user_id, company_profile_id) if `ticket` is a genuine,
    unexpired stream ticket - None for anything else (expired, malformed,
    wrong signature, or a normal access token missing the `purpose`
    claim, which this deliberately also rejects)."""
    try:
        payload = jwt.decode(ticket, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None

    if payload.get("purpose") != _TICKET_PURPOSE:
        return None

    sub = payload.get("sub")
    company_profile_id_raw = payload.get("company_profile_id")
    if sub is None or company_profile_id_raw is None:
        return None

    try:
        return uuid.UUID(sub), uuid.UUID(company_profile_id_raw)
    except ValueError:
        return None
