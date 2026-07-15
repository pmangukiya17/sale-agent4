import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProspectSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Every provider occurrence of a Prospect, preserved individually rather
    than collapsed into a flat list of provider keys. The same real-world
    company can be (and often will be) surfaced by more than one provider,
    or by the same provider more than once across different jobs - each
    occurrence gets its own row here with its own timestamp, URL, and
    provider_confidence, so a future reconciliation/AI pass can weight
    conflicting fields by how much to trust each source instead of only
    knowing "this came from providers X and Y" with no way to tell them
    apart.
    """

    __tablename__ = "prospect_sources"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(nullable=False)
    # Per-occurrence confidence - how much to trust THIS provider's THIS
    # hit, not a static per-provider setting. Lets future AI weight
    # providers differently when reconciling conflicting data.
    provider_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_result_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_provider_results.id", ondelete="SET NULL"), nullable=True
    )

    prospect: Mapped["Prospect"] = relationship(back_populates="sources")
