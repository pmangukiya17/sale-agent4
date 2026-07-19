"""
Notification worker - M8.5's third standalone process, structurally
identical to the Workflow Engine's own two workers (see
app/workflow_engine/event_dispatcher_worker.py's own docstring for the
precedent this deliberately mirrors): polls the platform Event stream
ordered by `sequence_no` (the true total order - see Event's own
docstring for why a timestamp/UUID alone isn't sufficient), for events
that have no NotificationDispatch row yet, and applies
create_notification_for_event() to each - a fresh DB session per event,
try/except/rollback/close per item so one bad event never poisons the
loop for the next one.

Same single-instance, sequential-loop simplification already established
by every other worker in this project (no SELECT ... FOR UPDATE SKIP
LOCKED) - matches the actual single-replica docker-compose.yml reality
today (see event_dispatcher_worker.py's own docstring for the identical
reasoning, and where to extend this if the worker is ever scaled to
multiple replicas).

This worker is a pure Event CONSUMER - it never calls publish_event()
itself, and never imports a concrete domain package (see
app/notifications/__init__.py's own docstring for that boundary).
"""
import logging
import time as time_module

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import base as _base  # noqa: F401  (imports every model so relationship() string refs resolve)
from app.db.session import SessionLocal
from app.models.notification import NotificationDispatch
from app.models.workflow_event import Event
from app.notifications.service import create_notification_for_event

logger = logging.getLogger("sales_agent.notification_worker")


def process_one_event(db: Session, event: Event) -> dict[str, int]:
    """Applies create_notification_for_event() to one Event and commits
    once - the same "one commit per unit of work" shape as
    event_dispatcher_worker.process_one_event(). Returns counts for the
    caller's tick-level logging."""
    notification = create_notification_for_event(db, event)
    db.commit()
    return {"notified": 1, "skipped": 0} if notification is not None else {"notified": 0, "skipped": 1}


def run_one_tick() -> dict[str, int]:
    """One pass over the current backlog of Events with no
    NotificationDispatch row yet, up to NOTIFICATION_WORKER_BATCH_SIZE
    events, ordered by Event.sequence_no. "Not yet dispatched" means NO
    NotificationDispatch row exists for this event at all (a LEFT JOIN
    ... WHERE NULL, not a check against NotificationDispatch's own
    unique constraint) - identical query shape, and identical reasoning,
    to event_dispatcher_worker.run_one_tick()'s own EventConsumption
    poll."""
    db = SessionLocal()
    try:
        candidate_ids = list(
            db.scalars(
                select(Event.id)
                .outerjoin(NotificationDispatch, NotificationDispatch.event_id == Event.id)
                .where(NotificationDispatch.id.is_(None))
                .order_by(Event.sequence_no.asc())
                .limit(settings.NOTIFICATION_WORKER_BATCH_SIZE)
            )
        )
    finally:
        db.close()

    totals = {"notified": 0, "skipped": 0}
    for event_id in candidate_ids:
        # Fresh session per event - one event's failure must never
        # poison the transaction state for the next one, same discipline
        # as every other worker loop in this codebase.
        db = SessionLocal()
        try:
            event = db.get(Event, event_id)
            if event is not None:
                counts = process_one_event(db, event)
                for key, value in counts.items():
                    totals[key] = totals.get(key, 0) + value
        except Exception:  # noqa: BLE001 - the worker loop must survive one bad event
            logger.exception("Unhandled error creating notification for Event %s", event_id)
            db.rollback()
        finally:
            db.close()

    return totals


def run_forever() -> None:  # pragma: no cover - the loop itself isn't unit-testable
    logger.info(
        "Notification worker starting - poll_interval=%ss batch_size=%s",
        settings.NOTIFICATION_WORKER_POLL_INTERVAL_SECONDS,
        settings.NOTIFICATION_WORKER_BATCH_SIZE,
    )
    while True:
        try:
            counts = run_one_tick()
            if any(counts.values()):
                logger.info("Notification worker tick: %s", counts)
        except Exception:  # noqa: BLE001 - one bad tick must never kill the worker process
            logger.exception("Unhandled error in Notification worker tick")
        time_module.sleep(settings.NOTIFICATION_WORKER_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
