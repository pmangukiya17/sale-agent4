import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DeliveryQueueItemStatus


class DeliveryQueueItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One approved OutreachDraft's journey through delivery - "500 approved
    drafts -> 500 queue items", never scheduled individually outside a
    campaign. outreach_draft_id is RESTRICT (never delete a draft that's
    been queued, same reproducibility discipline as OutreachPlaybook/
    PromptVersion being RESTRICT-referenced by OutreachDraft) - but this
    row does NOT trust that FK to stay meaningful over time, because
    OutreachDraft.current_content is mutable in place (see M4 hardening
    note below). Everything actually needed to send is FROZEN onto this
    row at enqueue time instead:

    - frozen_content: a snapshot of OutreachDraft.current_content.assembled
      at the moment this item was created, not re-read live at send time.
    - frozen_draft_version: which OutreachDraft.version was frozen, for
      traceability.
    - recipient_email / recipient_timezone: snapshotted from
      ProspectContact at enqueue time, so delivery history stays accurate
      even if the contact record is edited afterwards.

    This is the concrete fix for the gap identified during M5 planning:
    M4's frontend/backend do not currently block editing current_content
    on an already-approved draft. Freezing here means that gap can be
    closed as a hardening item without this table's correctness depending
    on it - a queued item is provably what was approved when it was
    queued, regardless of what happens to the draft afterward.

    prospect_id/prospect_contact_id/company_profile_id are denormalized
    down from the draft, same "every Outreach entity carries these all the
    way down" convention documented in
    docs/architecture/future-milestones.md note #1 - lets this table (and
    a future cross-campaign queue dashboard) filter without joining back
    through OutreachDraft.

    claimed_at supports the SELECT...FOR UPDATE SKIP LOCKED dispatch
    pattern plus stale-claim reclaim: a worker that crashes mid-send leaves
    a row claimed_at-old, in SENDING - the worker's reconciliation pass
    resets any such row back to QUEUED/RETRY after a timeout.
    """

    __tablename__ = "delivery_queue_items"

    delivery_campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("delivery_campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    outreach_draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach_drafts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prospect_contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospect_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sending_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sending_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    frozen_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    frozen_draft_version: Mapped[int] = mapped_column(Integer, nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)

    status: Mapped[DeliveryQueueItemStatus] = mapped_column(
        Enum(
            DeliveryQueueItemStatus,
            name="delivery_queue_item_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=DeliveryQueueItemStatus.QUEUED,
        nullable=False,
        index=True,
    )
    scheduled_send_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    delivery_campaign: Mapped["DeliveryCampaign"] = relationship(back_populates="queue_items")
    # One-directional on purpose - OutreachDraft/Prospect/ProspectContact
    # are never edited to add a reciprocal back-reference here. M4 must
    # never know how delivery works; this FK points up at M4/M1's
    # entities, not the other way around - same precedent OutreachDraft
    # itself follows toward ProspectContact.
    outreach_draft: Mapped["OutreachDraft"] = relationship()
    sending_profile: Mapped["SendingProfile"] = relationship()
    events: Mapped[list["DeliveryEvent"]] = relationship(
        back_populates="delivery_queue_item", cascade="all, delete-orphan", order_by="DeliveryEvent.occurred_at"
    )
