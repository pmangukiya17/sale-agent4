import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WebsiteFinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    SUPERSEDED - do not use. Same M0-era, never-wired situation as
    Thread/Message (no route/service/frontend page references it),
    hanging off the stale Company model rather than the live
    Prospect/CompanyProfile model set. Discovery's real per-company
    findings live on Prospect (description/industry_raw etc.) and
    IntelligenceSnapshot, not here. See
    deferred-items-and-design-boundaries.md's legacy CRM entry.
    """

    __tablename__ = "website_findings"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_scrape_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    structured_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    scraped_at: Mapped[datetime | None] = mapped_column(nullable=True)

    company: Mapped["Company"] = relationship(back_populates="website_findings")
