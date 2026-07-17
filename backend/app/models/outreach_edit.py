import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OutreachEdit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Append-only audit log of every human change to an OutreachDraft's
    current_content. Never mutated after creation. This, together with
    OutreachDraft.ai_generated_content staying permanently frozen, is the
    complete answer to "how is AI history preserved through edits": the
    original is always recoverable, and every subsequent change is a
    timestamped, attributed, reversible-in-principle diff - not a silent
    overwrite. Regenerating a draft never touches this table; it creates a
    new OutreachDraft version instead.
    """

    __tablename__ = "outreach_edits"

    outreach_draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach_drafts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    edited_at: Mapped[datetime] = mapped_column(nullable=False)
    previous_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    new_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    edit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    outreach_draft: Mapped["OutreachDraft"] = relationship(back_populates="edits")
