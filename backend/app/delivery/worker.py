"""
The Delivery worker: a standalone polling loop, run as its own process
(a separate `worker` service in docker-compose, same image as the
backend, different CMD - see docker-compose.yml). This is the ONE new
architectural pattern M5 introduces that M1-M4 deliberately avoided
(see this package's __init__.py docstring) - everything else in this
codebase runs synchronously inside an API request.

Two responsibilities, kept intentionally thin - the real logic lives in
scheduler/policy.py (which items, in what order) and dispatch_service.py
(how one item actually gets sent):

1. Each tick: ask the configured SchedulingPolicy for the next due batch
   (claims them via SELECT...FOR UPDATE SKIP LOCKED, flips to SENDING),
   commit that claim so it's visible/locked across processes, then call
   dispatch_service.dispatch() for each claimed item in its own
   transaction.
2. Periodically: reclaim stale SENDING items - a worker that crashes
   between claiming an item and dispatch_service leaving it in a
   terminal/rescheduled state leaves it stuck in SENDING forever
   otherwise. Anything claimed longer than
   DELIVERY_WORKER_STALE_CLAIM_MINUTES ago gets reset to SCHEDULED (with
   scheduled_send_at = now, so it's picked up again next tick) and an
   event logged - it does NOT increment attempt_count, since this is
   worker infrastructure recovering from its own failure, not a delivery
   attempt that actually reached the provider.

Executed for the first time during M5 Layer 7 verification, which caught
a real bug: this is the THIRD process entrypoint sharing the declarative
Base (alongside the backend's `app.main` and Alembic's `env.py`), and it
was the only one of the three missing the `app.db.base` import both of
the others already carry specifically so every model gets registered
with SQLAlchemy before mapper configuration runs (see `app/main.py`'s
identical import, same comment). Without it, this process's import chain
only pulls in the handful of models dispatch_service/policy touch
directly - not the full graph - so the first ORM query in `run_one_tick`
triggers `configure_mappers()`, which walks every mapper registered so
far (including DeliveryCampaign's, since dispatch_service imports it) and
fails to resolve its `relationship("CompanyProfile")` string reference,
because CompanyProfile itself was never imported in this process. That
raised `sqlalchemy.exc.InvalidRequestError` on every single tick, before
`claim_next_batch` was ever reached - queue items stayed SCHEDULED
forever, silently, since `run_forever`'s outer try/except logs and
swallows exactly this kind of per-tick exception. A narrower fix (just
importing CompanyProfile) would only have deferred the same crash to the
next unresolved relationship (OutreachDraft, ProviderCredential, etc.) -
the worker process needs the complete model graph registered, the same
way the backend and Alembic already do.
"""
import logging
import time as time_module
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.db import base as _base  # noqa: F401  (imports every model so relationship() string refs resolve - see module docstring)
from app.db.session import SessionLocal
from app.delivery import dispatch_service
from app.delivery.scheduler.registry import get_scheduling_policy
from app.models.delivery_event import DeliveryEvent
from app.models.delivery_queue_item import DeliveryQueueItem
from app.models.enums import DeliveryEventType, DeliveryQueueItemStatus

logger = logging.getLogger("sales_agent.delivery_worker")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_one_tick() -> int:
    """Claims and dispatches one batch. Returns the number of items
    processed, so the caller (the loop, or a test) can log/assert on it."""
    db = SessionLocal()
    try:
        policy = get_scheduling_policy(settings.DELIVERY_SCHEDULING_POLICY)
        claimed = policy.claim_next_batch(db, settings.DELIVERY_WORKER_BATCH_SIZE, _now())
        db.commit()
        claimed_ids = [item.id for item in claimed]
    finally:
        db.close()

    for item_id in claimed_ids:
        # Fresh session per item - one item's failure/exception must never
        # poison the transaction state for the next one in the batch.
        db = SessionLocal()
        try:
            item = db.get(DeliveryQueueItem, item_id)
            if item is not None:
                dispatch_service.dispatch(db, item)
        except Exception:  # noqa: BLE001 - the worker loop must survive one bad item
            logger.exception("Unhandled error dispatching DeliveryQueueItem %s", item_id)
            db.rollback()
        finally:
            db.close()

    return len(claimed_ids)


def reclaim_stale_claims() -> int:
    """Resets SENDING items whose claim is older than
    DELIVERY_WORKER_STALE_CLAIM_MINUTES back to SCHEDULED. Returns the
    number reclaimed."""
    cutoff = _now() - timedelta(minutes=settings.DELIVERY_WORKER_STALE_CLAIM_MINUTES)
    db = SessionLocal()
    try:
        stale_items = list(
            db.scalars(
                select(DeliveryQueueItem).where(
                    DeliveryQueueItem.status == DeliveryQueueItemStatus.SENDING,
                    DeliveryQueueItem.claimed_at.is_not(None),
                    DeliveryQueueItem.claimed_at < cutoff,
                )
            ).all()
        )
        for item in stale_items:
            item.status = DeliveryQueueItemStatus.SCHEDULED
            item.scheduled_send_at = _now()
            item.claimed_at = None
            db.add(
                DeliveryEvent(
                    delivery_queue_item_id=item.id,
                    event_type=DeliveryEventType.SCHEDULED,
                    detail={"reason": "stale_claim_reclaimed"},
                )
            )
        db.commit()
        return len(stale_items)
    finally:
        db.close()


def run_forever() -> None:  # pragma: no cover - the loop itself isn't unit-testable
    logger.info(
        "Delivery worker starting - poll_interval=%ss batch_size=%s policy=%s",
        settings.DELIVERY_WORKER_POLL_INTERVAL_SECONDS,
        settings.DELIVERY_WORKER_BATCH_SIZE,
        settings.DELIVERY_SCHEDULING_POLICY,
    )
    tick_count = 0
    while True:
        try:
            processed = run_one_tick()
            if processed:
                logger.info("Dispatched %d queue item(s)", processed)
            # Reclaim stale claims periodically rather than every tick -
            # roughly once a minute regardless of poll interval.
            if tick_count % max(1, 60 // max(1, settings.DELIVERY_WORKER_POLL_INTERVAL_SECONDS)) == 0:
                reclaimed = reclaim_stale_claims()
                if reclaimed:
                    logger.warning("Reclaimed %d stale SENDING item(s)", reclaimed)
        except Exception:  # noqa: BLE001 - one bad tick must never kill the worker process
            logger.exception("Unhandled error in delivery worker tick")
        tick_count += 1
        time_module.sleep(settings.DELIVERY_WORKER_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
