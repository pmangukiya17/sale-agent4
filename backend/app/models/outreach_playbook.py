import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OutreachPlaybook(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Replaces the originally-proposed "OutreachTemplate" entirely, per
    explicit refinement: a playbook is business knowledge ("how this
    company sells"), not a static text template. Versioned exactly like
    ICPCriteria - version/is_current are scoped per
    (company_profile_id, name), NOT per company_profile_id alone, because
    (unlike ICPCriteria in practice) a single business is expected to
    maintain several concurrently-current playbooks distinguished by
    name/playbook_goal (e.g. "Standard Meeting Request" vs "Partnership
    Outreach") - each name is its own independent version lineage.

    playbook_goal is a free string, not a closed enum, even though the
    approved examples (meeting_request/sample_request/partnership/
    supplier_outreach/follow_up) look like a fixed set: nothing in the
    engine branches logic on this value today (unlike channel_key, which
    selects a ChannelProvider class), it exists purely so a business can
    label/organize multiple playbooks - and per the explicit multi-business
    design goal, a future Trivoxa client should be able to invent a new
    goal label without a migration.

    derived_from_playbook_version preserves ancestry across regenerated
    versions (which version this one was edited from), per explicit
    refinement, for comparison/restoration/audit. is_current still governs
    which version is actually used at render time; derived_from is purely
    historical.

    company_profile_id stays nullable for system-seeded starter playbooks
    (is_system_default=True) that a business clones and customizes, the
    same convention as every *Template model since M1.

    Deliberately does NOT model SPIN/Challenger/MEDDICC or any other named
    sales methodology as structured fields or child tables - those live as
    prose in sales_methodology/communication_principles/PromptVersion
    guidance, never as schema, per explicit instruction.
    """

    __tablename__ = "outreach_playbooks"

    company_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    playbook_goal: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    derived_from_playbook_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_system_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Business knowledge - "how this business sells" - never AI instructions
    # (those live on PromptVersion instead; see that model's docstring).
    sales_methodology: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_voice: Mapped[str | None] = mapped_column(Text, nullable=True)
    core_value_proposition: Mapped[str | None] = mapped_column(Text, nullable=True)
    communication_principles: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    personalization_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Per-channel_key overrides (e.g. {"whatsapp": {"max_length": 300}}) -
    # free-shaped JSONB, same escape-hatch convention as ICPCriteria.rules.
    channel_preferences: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cta_strategy: Mapped[str | None] = mapped_column(Text, nullable=True)

    blocks: Mapped[list["OutreachBlock"]] = relationship(
        back_populates="outreach_playbook", cascade="all, delete-orphan", order_by="OutreachBlock.display_order"
    )
    outreach_requests: Mapped[list["OutreachRequest"]] = relationship(back_populates="outreach_playbook")
