"""
The Workflow Engine's one sanctioned way to publish an event -
publish_event() below. Part 1, Phase 1 of the approved implementation
plan: this module is the entire behavior surface of this phase, proven
in isolation (tests/test_workflow_events.py) before any real domain
module calls it.

Transactional outbox, exactly as approved (docs/architecture/
m7-workflow-engine-plan.md section 2, "Event publishing"): this function
deliberately does NOT commit. It only `db.add()`s (and flushes, to make
the row's generated id available to the caller immediately) an `Event`
row onto whatever Session the caller passes in - the caller's own
existing transaction is what commits it, atomically, alongside whatever
domain write the event is reporting. If the caller's transaction later
rolls back for any reason, the event is rolled back with it - there is
no separate connection, no separate commit, no window where the domain
write could succeed while the event is lost (or vice versa). This is the
whole point of an outbox: in this project's single-Postgres deployment,
the "outbox" and "the log the engine reads" are the same table and the
same transaction.

No caller should ever construct an `Event` row directly - this is the
one entry point, matching this project's existing "one shared helper,
not scattered call sites" discipline (e.g. `_log_event` in
app.delivery.dispatch_service).

M8.5 Event Backbone: four new OPTIONAL keyword parameters below
(actor_type/actor_id/severity/category) - additive only. Every existing
caller (today: app.reply_intelligence.thread_builder's
CONVERSATION_CREATED_EVENT_TYPE publish) continues to work unchanged,
since none of the four are required and all default to None. See
app.models.workflow_event.Event's own docstring for what each means.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.workflow_event import Event


def publish_event(
    db: Session,
    *,
    event_type: str,
    company_profile_id: uuid.UUID,
    source: str,
    subject_type: str | None = None,
    subject_id: uuid.UUID | None = None,
    payload: dict | None = None,
    correlation_id: uuid.UUID | None = None,
    causation_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
    schema_version: int = 1,
    actor_type: str | None = None,
    actor_id: str | None = None,
    severity: str | None = None,
    category: str | None = None,
) -> Event:
    """Adds (and flushes, but does NOT commit) one Event row onto `db`.

    `event_type` and `payload` are entirely the caller's vocabulary - this
    function never validates or interprets either; it only stores them.
    `source` should identify the publishing module (e.g.
    `"app.delivery.dispatch_service"`) for debugging/explainability, not
    for routing - the engine never branches on it.

    `occurred_at` defaults to now (UTC) if not given - most callers won't
    pass it explicitly; it exists as a parameter for the rare case a
    caller is recording an event for something that happened at a
    slightly earlier, already-known timestamp.

    `actor_type`/`actor_id`, `severity`, `category` (M8.5) - all optional,
    all opaque to this function exactly like `event_type`/`payload` are;
    it only stores whatever the caller passes.
    """
    event = Event(
        event_type=event_type,
        company_profile_id=company_profile_id,
        source=source,
        subject_type=subject_type,
        subject_id=subject_id,
        payload=payload,
        correlation_id=correlation_id,
        causation_id=causation_id,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        schema_version=schema_version,
        actor_type=actor_type,
        actor_id=actor_id,
        severity=severity,
        category=category,
    )
    db.add(event)
    db.flush()
    return event
