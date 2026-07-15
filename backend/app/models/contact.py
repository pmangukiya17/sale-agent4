import uuid

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Contact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contacts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Same rationale as Company's timezone fields: unused until a future
    # Outlook scheduler reads them (recipient's timezone/hours, not the
    # sender's).
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    working_hours: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    preferred_contact_time: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    company: Mapped["Company"] = relationship(back_populates="contacts")
