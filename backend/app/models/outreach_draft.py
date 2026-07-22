import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OutreachDraftStatus


class OutreachDraft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    The core generated artifact - one rendered piece of outreach for one
    ProspectContact, on one channel. Versioned per
    (prospect_contact_id, channel_key) - never overwritten, same "never
    overwrite, always version" discipline as IntelligenceSnapshot/
    PersonalizationSnapshot. An email v3 and a LinkedIn v1 for the same
    contact are independent lineages.

    ai_generated_content is frozen forever after creation - the AI's
    original, untouched output, shaped as:
    {"blocks": [{"block_key": str, "behavior": str, "content": str,
                 "reasoning": str | None}, ...],
     "assembled": {...}}  # channel-shaped, e.g. {"subject", "body"} for email
    current_content starts as a copy of ai_generated_content and is the
    only mutable surface - every change to it is logged via a child
    OutreachEdit row (previous/new content snapshots), never overwritten
    silently. This is how "preserve AI history through edits" is answered:
    ai_generated_content never changes; current_content's evolution is a
    complete, append-only, reconstructable log.

    outreach_playbook_id + outreach_playbook_version freeze exactly which
    playbook version produced this draft, since playbooks are themselves
    versioned/mutable over time - same reproducibility discipline as
    personalization_snapshot referencing a frozen intelligence_snapshot
    version in M3's config_snapshot.

    status drives approval (draft -> pending_approval -> approved/rejected)
    independently of is_current; regenerating flips the previous
    is_current=True row to is_current=False and, if it was approved,
    status -> superseded (distinct from simply "old" - it records that
    something specifically replaced it).
    """

    __tablename__ = "outreach_drafts"

    outreach_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # RESTRICT, not CASCADE: an OutreachDraft is real AI-generated execution
    # history - see deferred-items-and-design-boundaries.md.
    prospect_contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospect_contacts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    outreach_playbook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach_playbooks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    outreach_playbook_version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prompt_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    rendered_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_generated_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    current_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[OutreachDraftStatus] = mapped_column(
        Enum(
            OutreachDraftStatus,
            name="outreach_draft_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=OutreachDraftStatus.DRAFT,
        nullable=False,
        index=True,
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    outreach_job: Mapped["OutreachJob | None"] = relationship()
    outreach_playbook: Mapped["OutreachPlaybook"] = relationship()
    prompt_version: Mapped["PromptVersion"] = relationship()
    prospect_contact: Mapped["ProspectContact"] = relationship()
    edits: Mapped[list["OutreachEdit"]] = relationship(
        back_populates="outreach_draft", cascade="all, delete-orphan", order_by="OutreachEdit.edited_at"
    )
    evidence: Mapped[list["OutreachEvidence"]] = relationship(
        back_populates="outreach_draft", cascade="all, delete-orphan"
    )
