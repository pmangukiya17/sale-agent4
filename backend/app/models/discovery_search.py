import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SearchDepth, SearchFrequency


class DiscoverySearch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A business's configured, runnable search: Search Template -> Search ->
    Job. Deliberately has NO relationship to Product - products are read
    directly from the CompanyProfile (all active ones) at run time via the
    bound ICPCriteria's company, so there's exactly one place ("what do we
    sell") instead of a second, duplicate configuration surface here.
    """

    __tablename__ = "discovery_searches"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Every search must derive from a template - this is a hard requirement
    # (Search Template -> Search -> Job), not an optional convenience.
    search_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("search_templates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Which ICP version to search against. Null = "use whichever version is
    # is_active on this company profile at run time"; set = pinned to one
    # specific historical version regardless of what's active later.
    icp_criteria_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("icp_criteria.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Overrides/merges on top of the template's query_spec.
    query_spec: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Which provider plugin keys are enabled for this search, e.g.
    # ["manual_csv"]. New providers are new registry entries, never a
    # schema change here.
    provider_keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    search_depth: Mapped[SearchDepth] = mapped_column(
        Enum(
            SearchDepth,
            name="search_depth",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SearchDepth.STANDARD,
        nullable=False,
    )
    # Stored now for forward-compatibility; nothing acts on this yet since
    # M1 is manual-execution-only (no scheduler/worker).
    search_frequency: Mapped[SearchFrequency] = mapped_column(
        Enum(
            SearchFrequency,
            name="search_frequency",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SearchFrequency.MANUAL,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    search_template: Mapped["SearchTemplate"] = relationship(back_populates="discovery_searches")
    icp_criteria: Mapped["ICPCriteria | None"] = relationship()
    jobs: Mapped[list["DiscoveryJob"]] = relationship(back_populates="discovery_search", cascade="all, delete-orphan")
    runs: Mapped[list["DiscoveryRun"]] = relationship(back_populates="discovery_search", cascade="all, delete-orphan")
