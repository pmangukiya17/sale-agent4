import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Thread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "threads"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    outlook_conversation_id: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)

    company: Mapped["Company"] = relationship(back_populates="threads")
    messages: Mapped[list["Message"]] = relationship(back_populates="thread", cascade="all, delete-orphan")
