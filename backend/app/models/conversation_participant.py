import uuid

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ConversationParticipantRole


class ConversationParticipant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One person on one Conversation, identified by email address - which
    means the same thing regardless of which provider the mailbox uses,
    so this table is provider-agnostic by construction (see
    docs/architecture/m6-reply-intelligence-plan.md section 2).

    A real table rather than a JSONB list on Conversation on purpose: B2B
    export deal threads (this app's own domain) routinely have multiple
    stakeholders CC'd in and out over time, and identity resolution
    (matching prospect_contact_id) needs to be correctable per-participant
    later without rewriting a blob.

    One row per (conversation, email) - see the unique constraint below.
    Mutable in place (role/prospect_contact_id can be corrected later),
    not versioned - this is structural metadata, not an evidence trail,
    same governance as SendingProfile/CompanyProfile rather than
    OutreachDraft/PromptVersion.

    prospect_contact_id is nullable - an inbound message may come from an
    address that doesn't match any known ProspectContact yet; the
    participant row still needs to exist so the message isn't dropped
    (see Conversation's docstring for the identical reasoning applied to
    prospect_id/prospect_contact_id there). Never silently promoted to a
    new ProspectContact automatically - that stays a human-confirmed
    action, same "AI recommends, human decides" boundary held everywhere
    else in this system.
    """

    __tablename__ = "conversation_participants"
    __table_args__ = (
        UniqueConstraint("conversation_id", "email", name="uq_conversation_participants_conversation_email"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[ConversationParticipantRole] = mapped_column(
        Enum(
            ConversationParticipantRole,
            name="conversation_participant_role",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    prospect_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospect_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="participants")
    prospect_contact: Mapped["ProspectContact | None"] = relationship()
