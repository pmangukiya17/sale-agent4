import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DiscoveryJobStatus


class DiscoveryJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One execution of a DiscoverySearch. In M1 this is always synchronous -
    created and completed within a single request/response cycle (no
    Celery/Redis/BackgroundTasks/polling worker yet) - but the status enum
    already includes PENDING/RUNNING/CANCELLED so a future async executor
    can populate this table without a schema change, only a different
    execution model.
    """

    __tablename__ = "discovery_jobs"

    discovery_search_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_searches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalized, matching how Product/ICPCriteria/KnowledgeBase are
    # scoped directly rather than requiring a join through the search.
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[DiscoveryJobStatus] = mapped_column(
        Enum(
            DiscoveryJobStatus,
            name="discovery_job_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=DiscoveryJobStatus.PENDING,
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    providers_used: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    raw_result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prospect_created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prospect_matched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # M8.8: real per-run scoring outcomes (migration 0018) - how many of
    # THIS run's touched prospects ended QUALIFIED vs UNQUALIFIED after
    # _score_and_apply(), for the Live Workflow Visualization's "Qualified
    # buyers" / "Rejected buyers" fields. Not derivable after the fact from
    # Prospect.status alone (a prospect's status can change on a LATER
    # run), so this is captured at the moment this specific job scores it.
    prospect_qualified_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prospect_rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Per-provider timing/status/error detail, one entry per provider run
    # (also mirrored as rows in discovery_job_provider_runs for querying).
    log: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    discovery_search: Mapped["DiscoverySearch"] = relationship(back_populates="jobs")
    provider_runs: Mapped[list["DiscoveryJobProviderRun"]] = relationship(
        back_populates="discovery_job", cascade="all, delete-orphan"
    )
    provider_results: Mapped[list["DiscoveryProviderResult"]] = relationship(
        back_populates="discovery_job", cascade="all, delete-orphan"
    )
    run: Mapped["DiscoveryRun | None"] = relationship(back_populates="discovery_job", uselist=False)
