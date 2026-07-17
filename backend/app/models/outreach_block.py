import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OutreachBlockBehavior


class OutreachBlock(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One reusable, composable piece of an OutreachPlaybook - e.g. greeting,
    company_introduction, capability_statement, core_value_proposition,
    opening_paragraph, prospect_relevance, cta, closing_sentence,
    signature. Belongs to exactly one playbook VERSION (not a standalone
    reusable-across-playbooks row): when a playbook is revised, its whole
    block set is cloned into the new version, same "never overwrite,
    parent-level versioning" discipline used everywhere else in this
    codebase - there is no separate per-block version history to manage.

    block_key is a free string, not an enum, for the same reason
    playbook_goal is: new block types (e.g. a future "video_script_intro")
    should never require a migration.

    behavior governs how the channel renderer treats this block at
    generation time: FIXED content is copied verbatim (per the explicit
    instruction that proven messaging like a capability statement or value
    proposition should not be rewritten every time); AI_ASSISTED lightly
    personalizes fixed_content; AI_GENERATED is written fresh from
    ai_guidance + the buyer's PersonalizationSnapshot. Per the explicit
    example, opening_paragraph/prospect_relevance/closing_sentence are the
    blocks expected to be AI_GENERATED; greeting/capability_statement/
    core_value_proposition/signature are expected to be FIXED.

    applicable_channels is nullable = applies to every channel; otherwise a
    JSONB list of channel_key strings this block is relevant to (e.g. a
    "signature" block might not apply to a terse WhatsApp message).
    """

    __tablename__ = "outreach_blocks"

    outreach_playbook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach_playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    behavior: Mapped[OutreachBlockBehavior] = mapped_column(
        Enum(
            OutreachBlockBehavior,
            name="outreach_block_behavior",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    # Used when behavior=FIXED (verbatim content) or as the starting point
    # for behavior=AI_ASSISTED (lightly personalized from this baseline).
    fixed_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Instructions for the AI on this specific block - used for
    # AI_ASSISTED/AI_GENERATED behaviors, ignored for FIXED.
    ai_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicable_channels: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    outreach_playbook: Mapped["OutreachPlaybook"] = relationship(back_populates="blocks")
