import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OutreachEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Real referential integrity for "why was this draft (or specific block
    of it) written this way" - references existing PersonalizationStrategy/
    Signal/Recommendation/IntelligenceSnapshot rows by id, same pattern as
    SignalEvidence/RecommendationEvidence/PersonalizationEvidence before
    it. Deliberately does not duplicate any upstream content - Research
    owns raw evidence, Personalization owns strategy evidence, Outreach
    owns rendering evidence, and none of the three ever copies another's
    data wholesale.

    block_key is nullable and, when set, attributes this specific evidence
    link to one block within the draft's ai_generated_content (e.g. "the
    opening_paragraph came from this Signal") rather than the draft as a
    whole - finer-grained explainability than M2/M3 needed, since M4's
    content is explicitly block-composed rather than one monolithic text.

    confidence_score (added per explicit refinement) lets future prompting
    filter/prioritize evidence by source reliability - not every signal is
    equally trustworthy (e.g. a website statement vs. an AI inference).
    Recorded per evidence link, not per Signal/Recommendation, because the
    same underlying fact can be cited with different confidence in
    different drafts depending on how directly it was used.
    """

    __tablename__ = "outreach_evidence"

    outreach_draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach_drafts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    personalization_strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personalization_strategies.id", ondelete="SET NULL"), nullable=True
    )
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="SET NULL"), nullable=True
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True
    )
    intelligence_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intelligence_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    outreach_draft: Mapped["OutreachDraft"] = relationship(back_populates="evidence")
    personalization_strategy: Mapped["PersonalizationStrategy | None"] = relationship()
    signal: Mapped["Signal | None"] = relationship()
    recommendation: Mapped["Recommendation | None"] = relationship()
    intelligence_snapshot: Mapped["IntelligenceSnapshot | None"] = relationship()
