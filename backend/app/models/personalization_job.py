import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PersonalizationJobStatus


class PersonalizationJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One execution of a PersonalizationRequest. Synchronous only, same as
    Discovery (M1) and Research (M2) - created and completed within a
    single request/response cycle. No Celery/Redis/BackgroundTasks/
    polling worker. Unlike DiscoveryJob/ResearchJob there is no
    provider_runs child - Personalization has nothing to fetch, only one
    internal engine call to make.
    """

    __tablename__ = "personalization_jobs"

    personalization_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personalization_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[PersonalizationJobStatus] = mapped_column(
        Enum(
            PersonalizationJobStatus,
            name="personalization_job_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=PersonalizationJobStatus.PENDING,
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    log: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # M8.11 (migration 0020): real per-run count of strategies this job's
    # synthesis pass generated - the Live Workflow Visualization's
    # equivalent of Discovery's qualified/rejected counts and Research's
    # signal/recommendation counts.
    strategy_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    personalization_request: Mapped["PersonalizationRequest"] = relationship(back_populates="jobs")
    run: Mapped["PersonalizationRun | None"] = relationship(back_populates="personalization_job", uselist=False)
    # No back_populates here - PersonalizationSnapshot.personalization_job is
    # one-directional, exact same asymmetry as IntelligenceSnapshot.research_job
    # in M2 (a job doesn't need to look up "the snapshot it produced").
