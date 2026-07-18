import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Thread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    SUPERSEDED - do not use. This is an M0-era, never-wired table (no
    route/service/frontend page references it) hanging off the stale
    Company model, not the live Prospect/CompanyProfile model set - see
    future-milestones.md note 8 and m6-reply-intelligence-plan.md section
    9. M6 builds Conversation/EmailMessage against Prospect/CompanyProfile
    instead, deliberately not reusing this table or its Outlook-specific
    outlook_conversation_id column name. Kept (not dropped) only because
    Company still relates to it; slated for an actual DROP TABLE in a
    later cleanup migration once confirmed safe.
    """

    __tablename__ = "threads"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    outlook_conversation_id: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)

    company: Mapped["Company"] = relationship(back_populates="threads")
    messages: Mapped[list["Message"]] = relationship(back_populates="thread", cascade="all, delete-orphan")
