import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DiscoveryJobProviderRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Execution metrics for one provider call within one DiscoveryJob. A job
    can enable several providers, each gets its own row here - this is
    what "track duration, provider, api cost, token usage, requests" means
    concretely: per-provider, not just a job-level total.
    """

    __tablename__ = "discovery_job_provider_runs"

    discovery_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Numeric (not Float) since this is a real cost figure, not a score -
    # avoids floating point drift on money.
    api_cost: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    # Relevant for LLM-backed providers; null for plain HTTP/scrape providers.
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="completed")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    discovery_job: Mapped["DiscoveryJob"] = relationship(back_populates="provider_runs")
