import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OutreachJobStatus


class OutreachJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One execution of an OutreachRequest - synchronous only, same as every
    prior milestone's Job model. No provider_runs child (Outreach fetches
    nothing external; rendering is one internal channel-provider call).

    personalization_snapshot_id is the explainability/staleness anchor:
    exactly which PersonalizationSnapshot version this render read, so
    "this draft was generated from strategy v1, the current one is now v2"
    stays answerable. prompt_version_id records exactly which AI-behavior
    instructions were in effect. Both are nullable/SET NULL so job history
    survives even if a referenced row is later deleted, but are populated
    on every successful run.
    """

    __tablename__ = "outreach_jobs"

    outreach_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prospect_contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospect_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    personalization_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personalization_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prompt_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[OutreachJobStatus] = mapped_column(
        Enum(
            OutreachJobStatus,
            name="outreach_job_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=OutreachJobStatus.PENDING,
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    log: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    outreach_request: Mapped["OutreachRequest"] = relationship(back_populates="jobs")
    personalization_snapshot: Mapped["PersonalizationSnapshot | None"] = relationship()
    prompt_version: Mapped["PromptVersion | None"] = relationship(back_populates="outreach_jobs")
    run: Mapped["OutreachRun | None"] = relationship(back_populates="outreach_job", uselist=False)
    # No back_populates here - OutreachDraft.outreach_job is one-directional,
    # same asymmetry as PersonalizationSnapshot.personalization_job in M3.
