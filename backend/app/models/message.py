import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import MessageDirection


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    SUPERSEDED - do not use. See Thread's docstring (same table family,
    same reasoning) - this is replaced by EmailMessage
    (app/models/email_message.py, migration 0009), built provider-
    agnostically against Conversation/Prospect/CompanyProfile rather than
    this table's stale Company/Thread parent and Outlook-specific
    outlook_message_id column. Kept only because Thread still relates to
    it; slated for an actual DROP TABLE in a later cleanup migration once
    confirmed safe.
    """

    __tablename__ = "messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(
            MessageDirection,
            name="message_direction",
            # Same fix as User.role: bind the enum's lowercase VALUE, not
            # its uppercase NAME, to match the Postgres type from migration 0001.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    outlook_message_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    classification: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="e.g. interested, not_interested, bounce, auto_reply"
    )

    thread: Mapped["Thread"] = relationship(back_populates="messages")
