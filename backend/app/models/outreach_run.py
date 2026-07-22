import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OutreachRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Frozen, permanent record of one OutreachRequest execution - exact
    mirror of PersonalizationRun/ResearchRun/DiscoveryRun. Records exactly
    which OutreachPlaybook version, PromptVersion, PersonalizationSnapshot
    version, and channel were used, so "why does this draft say X" stays
    answerable even after those upstream rows change."""

    __tablename__ = "outreach_runs"

    outreach_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    outreach_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach_jobs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # RESTRICT, not CASCADE: this is the "Frozen, permanent record" this
    # class's own docstring describes - see
    # deferred-items-and-design-boundaries.md.
    prospect_contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospect_contacts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    triggered_at: Mapped[datetime] = mapped_column(nullable=False)
    config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    outreach_draft_version_created: Mapped[int | None] = mapped_column(Integer, nullable=True)

    outreach_request: Mapped["OutreachRequest"] = relationship(back_populates="runs")
    outreach_job: Mapped["OutreachJob"] = relationship(back_populates="run")
