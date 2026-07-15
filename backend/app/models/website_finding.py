import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WebsiteFinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "website_findings"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_scrape_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    structured_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    scraped_at: Mapped[datetime | None] = mapped_column(nullable=True)

    company: Mapped["Company"] = relationship(back_populates="website_findings")
