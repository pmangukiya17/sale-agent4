import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ConversationStatus, ReplyStatus


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One durable thread, scoped to a business relationship, not a mailbox
    or a provider - see docs/architecture/m6-reply-intelligence-plan.md
    section 2. If a connected mailbox is ever reconnected, disconnected
    and replaced, or the business switches providers entirely,
    conversation history must survive that change unaffected; nothing on
    this row is provider-specific (provider identity lives on EmailMessage,
    per-message, not here).

    prospect_id and prospect_contact_id are BOTH nullable, correcting an
    earlier draft of the M6 plan that made prospect_id required - if
    identity resolution can't match a known ProspectContact, it usually
    can't identify the Prospect either, and a NOT NULL prospect_id would
    make an unrecognized-sender's message unstorable, which contradicts
    this milestone's own "never silently drop a message" design intent.
    company_profile_id is the only required scope anchor: even a fully
    unresolved conversation was still observed through one business's
    connected mailbox.

    conversation_key is the conversation-builder's own derived correlation
    key (M6.3), not any one provider's native thread id verbatim - stored
    as a plain, writable column (never a Postgres GENERATED column) since
    thread-detection is a layered, cross-row heuristic that can't be
    expressed as a per-row SQL expression. M6.1 declares and indexes this
    column but never computes it - that arrives in M6.3.

    status is deliberately just OPEN/CLOSED (see ConversationStatus's own
    docstring) - M6.1 sets every row to the default OPEN and never
    transitions it; nothing here anticipates M6.3/M7 workflow logic.

    One-directional relationships only, matching the "point up, never
    down" boundary DeliveryQueueItem already established toward
    OutreachDraft/Prospect/ProspectContact one milestone down - Prospect,
    ProspectContact, ProviderConnection, and CompanyProfile are never
    edited to add a reciprocal back-reference to this table.

    reply_status/last_reply_at/last_reply_from/needs_human_review
    (migration 0012, M6.4) - written exclusively by
    app/reply_intelligence/reply_intelligence_worker.py, never by Thread
    Builder or dispatch_service. All four describe the MOST RECENT inbound
    reply only - this is a rolling current-state snapshot, not a
    per-message history (see ReplyStatus's own docstring for why a
    separate versioned analysis table was explicitly rejected for M6.4).
    All four are nullable/default-false: a Conversation with no inbound
    reply yet has reply_status/last_reply_at/last_reply_from = NULL and
    needs_human_review = false, which is a real, valid, common state (an
    outbound-only conversation awaiting a first reply), not an unset/
    not-yet-processed marker - there is deliberately no separate
    "analyzed" flag anywhere; see reply_intelligence_worker.py's own
    docstring for how it decides what to (re)process without one.
    """

    __tablename__ = "conversations"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    prospect_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospect_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_connections.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Not unique - two genuinely distinct conversations can legitimately
    # compute the same fallback key (subject-normalization + participant
    # match is a heuristic, not a guarantee) - see this column's own
    # composite index below, indexed for fast lookup, never constrained.
    conversation_key: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)

    status: Mapped[ConversationStatus] = mapped_column(
        Enum(
            ConversationStatus,
            name="conversation_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ConversationStatus.OPEN,
        nullable=False,
        index=True,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    first_discovered_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # --- M6.4: Reply Intelligence --------------------------------------
    reply_status: Mapped[ReplyStatus | None] = mapped_column(
        Enum(
            ReplyStatus,
            name="reply_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
        index=True,
    )
    last_reply_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    last_reply_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
    needs_human_review: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)

    company_profile: Mapped["CompanyProfile"] = relationship()
    prospect: Mapped["Prospect | None"] = relationship()
    prospect_contact: Mapped["ProspectContact | None"] = relationship()
    provider_connection: Mapped["ProviderConnection"] = relationship()

    messages: Mapped[list["EmailMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="EmailMessage.sent_at"
    )
    participants: Mapped[list["ConversationParticipant"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
