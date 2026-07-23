import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MailboxBrief(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Track C5 (dashboard-capabilities-architecture-plan.md, Section 6): a
    persisted, on-demand AI-generated executive summary of one business's
    workspace - conversations needing attention, top cross-portfolio
    recommendations, and the Opportunity pipeline's current shape. Per
    the CEO's explicit direction, this is PERSISTED (not regenerated on
    every page load) - each row is a durable snapshot, created only by an
    explicit "Generate New Brief" action
    (app/api/routes/mailbox_brief.py's POST .../generate route), never a
    GET side effect. Reading the latest one (GET .../mailbox-brief) never
    creates a row.

    A pure PROJECTION over already-existing CRM data (Conversation,
    Recommendation, Opportunity/OpportunityStageHistory) - per the CEO's
    explicit instruction, this table never duplicates that data. No raw
    email/message content is stored here either, carrying forward the
    privacy constraint `future-milestones.md` note 9 originally specified
    ("must not introduce a table that caches fetched email bodies or
    threads beyond the single request/response cycle") - only the AI's
    generated summary output and the numeric context it was computed
    from, never the underlying conversation text itself.

    ai_provider/ai_model are both plain strings, not enums - the same
    "adding a new provider must be a code+registry change, never a
    migration" convention `ProviderConnection.provider_key`/
    `SendingProfile.provider_key` already established, per the CEO's
    explicit "provider-agnostic... support future OpenAI/Claude/Gemini/
    internal models without schema changes" requirement. See
    app/mailbox_brief/engine/ for the pluggable engine interface that
    writes these two fields - exactly one concrete engine
    (DeterministicMailboxBriefEngine) exists today, mirroring the same
    "deterministic stub now, real LLM engine later, zero schema change"
    precedent `app/personalization/engine/deterministic_stub.py` already
    set for this project.

    recommendations/statistics are both JSONB - schema-less by design so
    a future real AI engine's richer output shape doesn't force a
    migration, the same "escape hatch" convention already used elsewhere
    in this codebase (e.g. OutreachJob.log, DeliveryEvent.detail).
    """

    __tablename__ = "mailbox_briefs"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    generated_at: Mapped[datetime] = mapped_column(nullable=False, index=True)

    ai_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    ai_model: Mapped[str] = mapped_column(String(100), nullable=False)

    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # List of {title, rationale, source_type, source_id} dicts - concrete,
    # traceable-back-to-real-data action items, never free-floating advice
    # with nothing behind it. See BriefOutcome.recommendations's own
    # docstring (app/mailbox_brief/engine/base.py) for the exact shape
    # the deterministic engine produces.
    recommendations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Raw counts/figures the summary and recommendations were computed
    # from (conversation_count, needs_review_count, open_opportunity_count,
    # pipeline_value breakdown, etc.) - transparency into what fed this
    # brief, not a second copy of the underlying rows themselves.
    statistics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    company_profile: Mapped["CompanyProfile"] = relationship()
    requested_by_user: Mapped["User | None"] = relationship()
