import uuid
from datetime import time

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DeliveryCampaignStatus


class DeliveryCampaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    "Send these N approved OutreachDrafts through this SendingProfile" -
    plays the role Request plays in M1-M4's Template->Request->Job->Run
    chain, but M5 deliberately does not reuse that three-table shape: that
    pattern encodes one synchronous execution per request, which is
    precisely the model M5 breaks from (one campaign fans out into many
    independently-dispatched DeliveryQueueItems). See
    docs/architecture/future-milestones.md note #1 - this is also the
    "Scheduling" layer of the eventually-planned top-level Campaign domain;
    a future Campaign entity can reference this by id with no redesign.

    Window/gap/limit fields are OPTIONAL overrides - null falls back to the
    referenced SendingProfile's own defaults, same override convention
    PromptVersion uses for business-specific vs. system-default prompts.

    priority is unused by M5's FIFO SchedulingPolicy - added now, cheap,
    exactly like OutreachRequest.sequence_key/sequence_position were added
    unused in M4 for a future M7 - so a future priority-based
    SchedulingPolicy needs zero schema change to read it.
    """

    __tablename__ = "delivery_campaigns"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sending_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sending_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[DeliveryCampaignStatus] = mapped_column(
        Enum(
            DeliveryCampaignStatus,
            name="delivery_campaign_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=DeliveryCampaignStatus.DRAFT,
        nullable=False,
        index=True,
    )

    sending_window_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    sending_window_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    min_gap_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_gap_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hourly_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Whether the scheduler should target the RECIPIENT's local business
    # hours (via the timezone resolver) or just the SendingProfile's own
    # window verbatim, ignoring recipient timezone entirely.
    respect_recipient_timezone: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Forward-compat only - see docstring. Not read by FIFOSchedulingPolicy.
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    company_profile: Mapped["CompanyProfile"] = relationship()
    sending_profile: Mapped["SendingProfile"] = relationship()
    queue_items: Mapped[list["DeliveryQueueItem"]] = relationship(
        back_populates="delivery_campaign", cascade="all, delete-orphan"
    )
