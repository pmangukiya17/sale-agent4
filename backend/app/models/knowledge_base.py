import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KnowledgeBase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Long-term memory for AI agents acting on behalf of a CompanyProfile -
    anything worth remembering that isn't a structured field elsewhere
    (past buyer objections, pricing notes, factory quirks, etc.).
    """

    __tablename__ = "knowledge_base"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)

    company_profile: Mapped["CompanyProfile"] = relationship(back_populates="knowledge_base_entries")
