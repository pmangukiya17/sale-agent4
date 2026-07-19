import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A user-facing notification - one CONSUMER of the platform Event
    stream (app.models.workflow_event.Event), never a second source of
    truth. References the Event it was generated from rather than
    duplicating its payload/subject/timestamp - per the approved M8.5
    architecture: "Notifications should reference Events instead of
    duplicating information... Events remain the source of truth."

    `title`/`message` ARE stored here (not derived at read-time from the
    Event) because they're genuinely notification-specific presentation
    concerns the Event correctly has no opinion on - rendered once, at
    creation time, by app.notifications.rules (the one place that maps
    an event_type to notification copy), not duplicated business data.
    Drilling into the full event (`event_id`) is how a caller gets back
    to the actual fact being reported.

    Exactly one Notification may exist per Event - see
    NotificationDispatch below for why that's enforced via a SEPARATE
    table rather than a unique constraint on this one, mirroring the
    EventConsumption precedent's own reasoning (M7.1).

    `user_id` nullable from day one, unused by anything in M8.5 itself -
    same "add the column now so a later milestone needs a service-logic
    change, not a migration" convention already used elsewhere in this
    codebase (e.g. PersonalizationScope.CONTACT). Every notification
    created in M8.5 is workspace-wide (`user_id IS NULL`); per-user
    targeting is a real, disclosed future capability, not built yet.
    """

    __tablename__ = "notifications"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Plain string, not a Postgres enum - same "domain owns the
    # vocabulary" convention as Event.severity/category (M8.5). Expected
    # values today: "low"/"medium"/"high"/"critical".
    priority: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)

    event: Mapped["Event"] = relationship()
    company_profile: Mapped["CompanyProfile"] = relationship()


class NotificationDispatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One record of the Notification worker (app.notifications.worker)
    having decided whether one Event should become a Notification -
    exactly the same role EventConsumption plays for the Workflow
    Engine's Event Dispatcher (M7.1), and for exactly the same reason:
    "no Notification row exists for this event yet" is ambiguous between
    "not processed yet" and "processed, the rules said don't notify" -
    this table is what removes that ambiguity, so the worker's own poll
    query (`NOT EXISTS (SELECT 1 FROM notification_dispatches WHERE
    event_id = events.id)`) is a correct, idempotent "still needs
    processing" check, mirroring event_dispatcher_worker.py's own query
    shape exactly.

    UniqueConstraint(event_id) - unlike EventConsumption (which can
    legitimately produce multiple rows per event, one per
    WorkflowInstance touched), each Event here maps to AT MOST ONE
    dispatch decision. `notification_id` is set only when
    decision="notified".
    """

    __tablename__ = "notification_dispatches"
    __table_args__ = (UniqueConstraint("event_id", name="uq_notification_dispatches_event_id"),)

    # No separate index=True here - the UniqueConstraint above (a
    # single-column uniqueness, unlike EventConsumption's composite one)
    # already provides an index that serves the worker's own by-event_id
    # lookup; a second plain index on the same column would be redundant
    # (matches migration 0013's own discipline against exactly that).
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
    )
    notification_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)  # "notified" | "skipped"
    dispatched_at: Mapped[datetime] = mapped_column(nullable=False)

    event: Mapped["Event"] = relationship()
    notification: Mapped["Notification | None"] = relationship()
