import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IntelligenceSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    An immutable, point-in-time capture of everything known about a
    Prospect - never edited after creation. version auto-increments per
    prospect (same pattern as ICPCriteria.version); exactly one row per
    prospect has is_current=True. "Snapshot" rather than "Prospect
    Intelligence" precisely because every row is a frozen moment, not an
    evolving record - comparing version N to N-1 is how "previous vs
    current research" is answered, by reading two rows, not by mutating one.

    Holds only descriptive facts (company/buyer/signals-summary).
    Prescriptive outputs (recommended products, sales angle) live in
    Recommendation instead - kept separate so a rep dismissing one
    recommendation never touches the snapshot it came from.
    """

    __tablename__ = "intelligence_snapshots"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    research_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Company
    business_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    products_offered: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    markets_served: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    certifications: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    manufacturing_or_trading: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sustainability_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_export_activity: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Buyer - decision-makers themselves are the existing ProspectContact
    # rows (M1); this is narrative context on top of them, not a duplicate.
    buyer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    procurement_structure: Mapped[str | None] = mapped_column(Text, nullable=True)
    purchasing_process: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Business signals narrative synthesis - the individual atomic,
    # evidenced signals live in the Signal table, not duplicated here.
    signals_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    prospect: Mapped["Prospect"] = relationship()
    research_job: Mapped["ResearchJob | None"] = relationship()
    signals: Mapped[list["Signal"]] = relationship(back_populates="intelligence_snapshot")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="intelligence_snapshot")
    reports: Mapped[list["ResearchReport"]] = relationship(back_populates="intelligence_snapshot")
