from sqlalchemy import Enum, Float, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PipelineStage


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    DEPRECATED - Phase 1 (see
    deferred-items-and-design-boundaries.md's legacy CRM entry). This is
    the M0-era, tenant-unscoped CRM company record - not company-profile-
    scoped like everything built since M1, and a confirmed strict subset
    of Prospect's field set. Unlike Thread/Message, this table is still
    live (companies.py routes, Pipeline.tsx) so it is NOT "do not use" -
    it's "do not build new development against this; use Prospect
    instead." Phase 2 (verify zero remaining dependencies, then drop)
    is a future milestone, not this one.
    """

    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Where this lead was discovered, e.g. 'manual', 'trade_data'"
    )
    legitimacy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    icp_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    stage: Mapped[PipelineStage] = mapped_column(
        Enum(
            PipelineStage,
            name="pipeline_stage",
            # Same fix as User.role: bind the enum's lowercase VALUE, not
            # its uppercase NAME, to match the Postgres type from migration 0001.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=PipelineStage.DISCOVERED,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Timezone/scheduling fields: not populated or used by anything yet.
    # Added now so the Discovery Engine (auto-detects timezone) and a future
    # Outlook scheduler (reads recipient timezone/hours) don't need a schema
    # change later - just business logic.
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    working_days: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    business_hours: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    website_findings: Mapped[list["WebsiteFinding"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    threads: Mapped[list["Thread"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    followups: Mapped[list["FollowUp"]] = relationship(back_populates="company", cascade="all, delete-orphan")
