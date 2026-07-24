"""
Shared test teardown helper - NOT a test module itself (no `test_`
prefix, never auto-discovered/collected by `python -m unittest
discover` or an explicit `tests.event_backbone_cleanup` invocation).

Deletes every row that has a live foreign key to `events.id` - as of
this writing that is the complete set: EventConsumption.event_id,
Notification.event_id, NotificationDispatch.event_id (all three
ondelete=RESTRICT - see each model's own ForeignKey declaration; this
project's standing "archive-over-delete / RESTRICT-not-CASCADE"
convention, not something to work around) - then the Event rows
themselves.

Why this exists (read before hand-rolling a fourth, partial copy of
this cleanup in a new test file): several Discovery test tearDowns used
to delete only WHICHEVER of these three tables had actually caused a
ForeignKeyViolation that day - EventConsumption first, then Notification/
NotificationDispatch next - rather than the complete, schema-derived
set. That is exactly the "patch one child table at a time" pattern
flagged during this project's own M2 Phase 2 verification. This module
is the one, complete implementation instead: ANY test whose fixtures
create Event rows - directly, or indirectly via
app.workflow_engine.events.publish_event() (every Discovery job run
publishes progress events; every route wired to the M7 Workflow Engine
publishes a trigger event) - should call
delete_events_and_dependents() at the point in its own tearDown where
it would otherwise delete Event rows itself. If a FOURTH table ever
gains a real FK to events.id, it is added HERE, once, rather than in
every test file that happens to hit the resulting violation first.

This also closes a real race, not just a "did I enumerate every table"
gap: this project's docker-compose stack runs event_dispatcher_worker/
step_runner_worker/the notification worker as REAL, always-on
background containers (see app/main.py's own lifespan docstring - the
realtime poller is the ONLY background task that runs in-process;
every other one is its own continuously-running worker service). Those
workers poll and consume `events` independently of any one test's own
explicit run_one_tick() calls, so a fresh EventConsumption/Notification/
NotificationDispatch row can appear for one of a test's own Events at
any point after that Event was created - including, in principle,
between this function's own dependents-delete and its own Event-delete
a few lines later. Calling this function as the LAST thing a tearDown
does before touching CompanyProfile/User - and never splitting its two
steps apart with other, unrelated cleanup work in between, the mistake
the earlier per-file patches made - keeps that window as tight as a
synchronous teardown running against a live shared database can. It
does not eliminate the race with mathematical certainty (nothing
running in a separate test process against always-on background
workers can, short of pausing those workers themselves - out of scope
for a test-only fix); it is the correct, standard mitigation, not a
false guarantee.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.event_consumption import EventConsumption
from app.models.notification import Notification, NotificationDispatch
from app.models.workflow_event import Event


def delete_events_and_dependents(db: Session, *, company_profile_id: uuid.UUID) -> None:
    """Deletes EventConsumption/NotificationDispatch/Notification rows
    referencing any Event owned by this company_profile_id, then those
    Event rows themselves - the complete dependency graph beneath
    `events`, not a subset. Commits twice (dependents, then Event) since
    the dependents must be durably gone before the Event delete is even
    attempted - a rolled-back dependents delete would defeat the whole
    point of calling this immediately before the Event delete."""
    event_ids = select(Event.id).where(Event.company_profile_id == company_profile_id)

    # Order among these three does not matter relative to each other -
    # none references another via RESTRICT (NotificationDispatch.
    # notification_id -> notifications.id is SET NULL, not RESTRICT) -
    # but ALL three must be gone before the Event delete below.
    db.query(EventConsumption).filter(EventConsumption.event_id.in_(event_ids)).delete(synchronize_session=False)
    db.query(NotificationDispatch).filter(NotificationDispatch.event_id.in_(event_ids)).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.event_id.in_(event_ids)).delete(synchronize_session=False)
    db.commit()

    db.query(Event).filter(Event.company_profile_id == company_profile_id).delete(synchronize_session=False)
    db.commit()
