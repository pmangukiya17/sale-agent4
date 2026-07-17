import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PersonalizationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Frozen, permanent record of one PersonalizationRequest execution -
    exact mirror of ResearchRun/DiscoveryRun. Records exactly which
    IntelligenceSnapshot version, Signal/Recommendation ids, and ICP
    version were read at generation time, so "why did the strategy say X"
    stays answerable even after those upstream rows change."""

    __tablename__ = "personalization_runs"

    personalization_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personalization_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    personalization_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personalization_jobs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    triggered_at: Mapped[datetime] = mapped_column(nullable=False)
    config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    personalization_version_created: Mapped[int | None] = mapped_column(Integer, nullable=True)

    personalization_request: Mapped["PersonalizationRequest"] = relationship(back_populates="runs")
    personalization_job: Mapped["PersonalizationJob"] = relationship(back_populates="run")
