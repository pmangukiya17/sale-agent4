import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ResearchJobProviderRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Execution metrics for one research provider call within one
    ResearchJob - same shape as DiscoveryJobProviderRun (M1)."""

    __tablename__ = "research_job_provider_runs"

    research_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    api_cost: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="completed")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    research_job: Mapped["ResearchJob"] = relationship(back_populates="provider_runs")
