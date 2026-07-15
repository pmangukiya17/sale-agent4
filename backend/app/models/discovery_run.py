import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DiscoveryRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Frozen, permanent record of one execution of a DiscoverySearch: what
    exact configuration (template, ICP version, providers, depth) was in
    effect at that moment, and how many prospects it produced. Named
    "Discovery Run" rather than "Search History" - it's a per-execution
    snapshot, one row per run, the same granularity as DiscoveryJob (which
    it's 1:1 with), not a rolling log.

    DiscoveryJob tracks operational status while it's/just-after running
    (state, timing, errors). DiscoveryRun is what the review/audit UI reads
    afterwards - if DiscoverySearch's live config changes next month, this
    row still accurately reflects what actually produced these results.
    """

    __tablename__ = "discovery_runs"

    discovery_search_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_searches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    discovery_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_jobs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    triggered_at: Mapped[datetime] = mapped_column(nullable=False)
    # Frozen copy of search_template_id, icp_criteria_id (resolved version),
    # query_spec, provider_keys, search_depth at the moment this ran.
    config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    prospects_found_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_prospects_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    discovery_search: Mapped["DiscoverySearch"] = relationship(back_populates="runs")
    discovery_job: Mapped["DiscoveryJob"] = relationship(back_populates="run")
