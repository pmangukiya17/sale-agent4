import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ResearchReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A rendered artifact for a human reader, generated FROM an
    IntelligenceSnapshot (+ its Signals/Recommendations) - never an
    independent source of truth. content has no fields that aren't
    derived from the snapshot at generation time; regenerating creates a
    new row rather than editing an old one, same never-overwrite
    philosophy as everything else in this domain. intelligence_snapshot_id
    is NOT NULL - a report always has a snapshot it was generated from.
    """

    __tablename__ = "research_reports"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    intelligence_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intelligence_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    research_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_jobs.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Composed sections (company/buyer/signals/recommendations) for
    # flexible rendering - assembled by the report generator, never
    # hand-authored.
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(nullable=False)
    generated_by: Mapped[str] = mapped_column(String(255), nullable=False, default="system")

    prospect: Mapped["Prospect"] = relationship()
    intelligence_snapshot: Mapped["IntelligenceSnapshot"] = relationship(back_populates="reports")
    research_job: Mapped["ResearchJob | None"] = relationship()
