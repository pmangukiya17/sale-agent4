"""
In-process subscriber registry - the thing that actually holds "which
HTTP connections are open right now, and for which company_profile_id".
Deliberately a plain in-memory structure, not a new table (see
app/realtime/__init__.py's own docstring for why persisting this would
be meaningless) - it describes THIS process's live connections only.

One asyncio.Queue per connected client. poller.py is the only writer
(publish()); app/api/routes/realtime.py's streaming generator is the
only reader (subscribe()/unsubscribe(), draining its own queue). Nothing
else in this codebase should import BROADCASTER directly - every other
caller either publishes Events the normal way (publish_event(), entirely
unaware this package exists) or reads Notifications/Events via their own
REST endpoints.

Module-level singleton (BROADCASTER), same shape as ACTION_REGISTRY/
PROVIDER_REGISTRY elsewhere in this codebase - there is exactly one of
these per process, and this project runs exactly one backend process
(see this package's own docstring for why that's a structural
requirement here, not an incidental simplification to fix later).
"""
import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Broadcaster:
    _subscribers: dict[uuid.UUID, set["asyncio.Queue[dict[str, Any]]"]] = field(default_factory=dict)

    def subscribe(self, company_profile_id: uuid.UUID) -> "asyncio.Queue[dict[str, Any]]":
        """Registers one new queue for `company_profile_id` and returns
        it. Unbounded on purpose - a slow consumer backing up would be a
        genuine problem, but this platform's realistic event volume per
        workspace (business-lifecycle events, not high-frequency
        telemetry) makes an unbounded queue the simpler, adequate choice
        for this milestone; a maxsize + drop-oldest policy is a
        straightforward addition later if a real workspace's volume ever
        justifies it."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.setdefault(company_profile_id, set()).add(queue)
        return queue

    def unsubscribe(self, company_profile_id: uuid.UUID, queue: "asyncio.Queue[dict[str, Any]]") -> None:
        """Idempotent - safe to call even if the connection was already
        cleaned up, so the route's `finally` block never has to guard
        against double-unsubscribe."""
        subscribers = self._subscribers.get(company_profile_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            del self._subscribers[company_profile_id]

    def publish(self, company_profile_id: uuid.UUID, event_payload: dict[str, Any]) -> None:
        """Fans `event_payload` out to every currently-subscribed queue
        for this company_profile_id. A no-op (not an error) if nobody is
        currently connected for this workspace - the overwhelmingly
        common case, since most Events are published while nobody has a
        browser tab open. Called exclusively by poller.py, never
        directly by a route or by publish_event() itself."""
        for queue in self._subscribers.get(company_profile_id, ()):
            queue.put_nowait(event_payload)

    def subscriber_count(self, company_profile_id: uuid.UUID) -> int:
        """Observability helper - used by verify_m8_6.sh's smoke test to
        confirm a connection actually registered, without needing to
        parse SSE framing from the shell."""
        return len(self._subscribers.get(company_profile_id, ()))


BROADCASTER = Broadcaster()
