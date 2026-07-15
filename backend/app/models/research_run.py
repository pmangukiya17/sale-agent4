import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ResearchRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Frozen, permanent record of one ResearchRequest execution - exact
    mirror of DiscoveryRun (M1). What exact configuration (template,
    provider set) was in effect, and what it produced, surviving even if
    the live ResearchRequest/ResearchTemplate is edited afterwards."""

    __tablename__ = "research_runs"

    research_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False, unique=True
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
    documents_found_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    intelligence_version_created: Mapped[int | None] = mapped_column(Integer, nullable=True)

    research_request: Mapped["ResearchRequest"] = relationship(back_populates="runs")
    research_job: Mapped["ResearchJob"] = relationship(back_populates="run")
