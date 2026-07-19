import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EventConsumptionOutcome


class EventConsumption(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One record of the Event Dispatcher worker (Part 1, Phase 4) having
    processed one Event against one candidate outcome - the idempotency
    guarantee from docs/architecture/m7-workflow-engine-plan.md section 2
    ("Idempotency"), enforced at the database level via the
    UniqueConstraint below, not only by application-level care.

    `workflow_instance_id` is NULL only for outcome = NO_MATCH (the event
    matched no ACTIVE definition's trigger and resumed no WAITING
    instance - a real, expected, common outcome, not an error). For
    STARTED_NEW_INSTANCE/RESUMED_INSTANCE it is always set to the
    specific instance that was created/resumed.

    A single Event CAN legitimately produce more than one
    EventConsumption row - e.g. one event whose event_type both starts a
    brand-new instance for one WorkflowDefinition's trigger AND resumes
    a different, already-WAITING instance for an unrelated workflow. The
    UniqueConstraint(event_id, workflow_instance_id) below prevents the
    SAME event from being applied to the SAME non-null instance twice -
    it does NOT (and, being a standard SQL unique constraint, structurally
    cannot) deduplicate multiple NO_MATCH rows for the same event, since
    Postgres treats NULL values in a unique index as pairwise distinct,
    not equal to each other. This is a disclosed, accepted, harmless gap:
    a NO_MATCH row carries no state-changing side effect, so a duplicate
    NO_MATCH row (which could only happen if the dispatcher's own crash-
    and-retry logic reprocesses one event's "found nothing" outcome more
    than once) is a redundant audit entry, never a correctness bug. The
    Event Dispatcher's own "which events still need processing" query
    (event_dispatcher_worker.py, Part 1 Phase 4) is `NOT EXISTS (SELECT 1
    FROM event_consumptions WHERE event_id = events.id)` - i.e. "does ANY
    row exist for this event at all" - which is what actually keeps an
    event from being reprocessed forever, independent of this
    constraint's narrower guarantee.
    """

    __tablename__ = "event_consumptions"
    __table_args__ = (UniqueConstraint("event_id", "workflow_instance_id", name="uq_event_consumptions_event_instance"),)

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    workflow_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=True, index=True
    )

    outcome: Mapped[EventConsumptionOutcome] = mapped_column(
        Enum(
            EventConsumptionOutcome,
            name="event_consumption_outcome",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    consumed_at: Mapped[datetime] = mapped_column(nullable=False)

    event: Mapped["Event"] = relationship()
    workflow_instance: Mapped["WorkflowInstance | None"] = relationship()
