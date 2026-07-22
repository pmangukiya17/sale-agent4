import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ResearchJobStatus


class ResearchJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One execution of a ResearchRequest. Synchronous only in M2, same as
    Discovery in M1 - created and completed within a single request/
    response cycle. No Celery/Redis/BackgroundTasks/polling worker.
    """

    __tablename__ = "research_jobs"

    research_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[ResearchJobStatus] = mapped_column(
        Enum(
            ResearchJobStatus,
            name="research_job_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ResearchJobStatus.PENDING,
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sources_used: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    raw_document_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # M8.13 (migration 0019): real per-run AI-analysis outcomes - how many
    # Signal/Recommendation rows THIS job's analysis pass produced, for
    # the Live Workflow Visualization's equivalent of Discovery's
    # qualified/rejected counts (see DiscoveryJob.prospect_qualified_count).
    signal_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recommendation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    log: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    research_request: Mapped["ResearchRequest"] = relationship(back_populates="jobs")
    provider_runs: Mapped[list["ResearchJobProviderRun"]] = relationship(
        back_populates="research_job", cascade="all, delete-orphan"
    )
    sources: Mapped[list["ResearchSource"]] = relationship(back_populates="research_job", cascade="all, delete-orphan")
    analyses: Mapped[list["AIAnalysis"]] = relationship(back_populates="research_job", cascade="all, delete-orphan")
    run: Mapped["ResearchRun | None"] = relationship(back_populates="research_job", uselist=False)
