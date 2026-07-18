import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, UUIDPrimaryKeyMixin


class Attachment(UUIDPrimaryKeyMixin, Base):
    """
    Metadata only - filename/content_type/size_bytes/provider_attachment_id
    - never the file bytes themselves. M6.2's sync worker fetches this
    metadata alongside a message's other fields (see
    OutlookProvider.fetch_messages_incremental's docstring) but never
    downloads attachment content; nothing in this milestone needs it, and
    storing arbitrary binary content in Postgres is a decision deferred
    until a real consumer (e.g. an M6.4+ "summarize the attached PO" use
    case) actually needs the bytes, at which point provider_attachment_id
    is what a later fetch-on-demand call would use to retrieve them from
    the provider directly.

    No TimestampMixin/updated_at, same "an event/fact row that could be
    'updated' wouldn't be one" discipline as DeliveryEvent - an attachment
    row describes what was observed on one already-immutable EmailMessage
    at sync time, so only created_at is declared, directly, below.

    Deferred out of M6.1 (see email_message.py's docstring and the M6.1
    design memo) specifically because nothing in that phase's scope ever
    wrote to it - M6.1 shipped no sync engine, so an Attachment table would
    have been anticipatory schema with zero writers. M6.2's sync worker is
    the first real writer.
    """

    __tablename__ = "attachments"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    email_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Opaque, provider-scoped id (Graph attachment `id`) - only meaningful
    # together with the parent EmailMessage's own provider_message_id;
    # never assumed unique/dereferenceable on its own across providers.
    provider_attachment_id: Mapped[str | None] = mapped_column(String(500), nullable=True)

    email_message: Mapped["EmailMessage"] = relationship(back_populates="attachments")
