"""
SchedulingPolicy: decides WHICH due queue items the worker claims next and
in what order - deliberately separate from windows.py (which decides WHEN
a not-yet-scheduled item should fire) and from dispatch_service (which
decides HOW a claimed item actually gets sent). The worker never embeds
this decision itself; it always asks a policy. FIFO is the only concrete
policy in M5 - the brief is explicit that priority/round-robin/weighted
strategies are future work, not required now, but the abstraction exists
precisely so adding one later is a new class + a registry entry, never a
worker rewrite (the same plugin-registry pattern as
DiscoveryProvider/ChannelProvider).
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.delivery_queue_item import DeliveryQueueItem
from app.models.enums import DeliveryQueueItemStatus


class SchedulingPolicy(ABC):
    key: ClassVar[str]

    @abstractmethod
    def claim_next_batch(self, db: Session, limit: int, now: datetime) -> list[DeliveryQueueItem]:
        """Claims (SELECT...FOR UPDATE SKIP LOCKED, flips to SENDING,
        stamps claimed_at) up to `limit` due items, in this policy's
        priority order. Must run inside a transaction the caller controls
        - this function flushes but does not commit, so the caller
        decides when the claim becomes visible to other workers."""
        raise NotImplementedError


class FIFOSchedulingPolicy(SchedulingPolicy):
    """The only concrete policy in M5. Orders strictly by
    scheduled_send_at ascending (oldest-due-first) - DeliveryCampaign.
    priority is deliberately NOT read here; it's a forward-compat column
    for a future PriorityFirstPolicy, unused by this one."""

    key = "fifo"

    def claim_next_batch(self, db: Session, limit: int, now: datetime) -> list[DeliveryQueueItem]:
        stmt = (
            select(DeliveryQueueItem)
            .where(
                DeliveryQueueItem.status == DeliveryQueueItemStatus.SCHEDULED,
                DeliveryQueueItem.scheduled_send_at <= now,
            )
            .order_by(DeliveryQueueItem.scheduled_send_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        items = list(db.scalars(stmt).all())
        for item in items:
            item.status = DeliveryQueueItemStatus.SENDING
            item.claimed_at = now
        db.flush()
        return items
