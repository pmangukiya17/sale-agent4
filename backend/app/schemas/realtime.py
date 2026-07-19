from pydantic import BaseModel


class StreamTicketRead(BaseModel):
    """Response for POST /realtime/tickets - a short-lived, narrowly-
    scoped credential for the ONE connection type in this platform that
    can't use the normal Authorization header (see
    app/realtime/tickets.py's own docstring for why)."""

    ticket: str
    expires_in_seconds: int
