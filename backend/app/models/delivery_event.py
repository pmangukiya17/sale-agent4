import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, UUIDPrimaryKeyMixin
from app.models.enums import DeliveryEventType


class DeliveryEvent(UUIDPrimaryKeyMixin, Base):
    """
    Append-only history for one DeliveryQueueItem - same discipline as
    OutreachEdit/OutreachRun/ProspectTimelineEvent: rows are inserted,
    never updated or deleted. No TimestampMixin/updated_at for exactly
    that reason - an event that could be "updated" wouldn't be an event.

    Deliberately stays delivery-lifecycle-only (queued/scheduled/started/
    sent/retry/failed/cancelled). A future M6 (reply/open/click tracking)
    gets its OWN table referencing DeliveryQueueItem/ProspectContact by id,
    not new event_type values bolted on here - same "distinct record, not
    new columns on the existing one" precedent as the AI Decision Gate note
    in docs/architecture/future-milestones.md.
    """

    __tablename__ = "delivery_events"

    delivery_queue_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("delivery_queue_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[DeliveryEventType] = mapped_column(
        Enum(
            DeliveryEventType,
            name="delivery_event_type",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # Provider response snippet, error message, attempt number, etc. -
    # free-shaped, same escape-hatch convention used throughout (e.g.
    # OutreachJob.log, OutreachRun.config_snapshot).
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    delivery_queue_item: Mapped["DeliveryQueueItem"] = relationship(back_populates="events")
