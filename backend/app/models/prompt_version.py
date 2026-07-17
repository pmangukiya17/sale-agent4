import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PromptVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    AI BEHAVIOR, not business knowledge - deliberately separate from
    OutreachPlaybook per explicit instruction. Holds instructions like "use
    only verified research", "never invent facts", "respect the playbook",
    "generate structured output" - largely business-agnostic, versioned
    independently, append-only (never edited after creation; a revision is
    a new row with version+1).

    company_profile_id is nullable = a global/system-default prompt every
    business inherits (maintained centrally, once, across every Trivoxa
    Group client) - the same nullable-for-system-default convention as
    every *Template model, but here the expectation is that MOST prompts
    stay global; a business only gets its own row if it genuinely needs
    different AI guardrails.

    A rendered prompt is never reconstructed later from this row alone -
    OutreachDraft.rendered_prompt freezes the exact, fully-substituted text
    actually used at generation time, so prompt_text can keep evolving
    without breaking the ability to audit what any past draft actually saw.
    """

    __tablename__ = "prompt_versions"

    company_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    channel_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    outreach_jobs: Mapped[list["OutreachJob"]] = relationship(back_populates="prompt_version")
