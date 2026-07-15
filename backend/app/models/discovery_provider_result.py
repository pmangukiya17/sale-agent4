import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DiscoveryProviderResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Append-only staging record of exactly what a provider returned, one row
    per raw hit, never overwritten. This is what "preserve raw provider
    data for future AI enrichment" means structurally - even after dedup
    and scoring collapse several of these into one Prospect, every
    original payload that contributed to it is still here untouched.
    """

    __tablename__ = "discovery_provider_results"

    discovery_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Provider-specific fields mapped into a common shape (name/website/
    # country/description/...) before dedup and scoring run against it.
    normalized_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    dedup_key: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    matched_prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    discovery_job: Mapped["DiscoveryJob"] = relationship(back_populates="provider_results")
