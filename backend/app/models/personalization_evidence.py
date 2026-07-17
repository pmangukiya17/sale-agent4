import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PersonalizationEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Real referential integrity for "why does this strategy say X" -
    references existing Signal/Recommendation/IntelligenceSnapshot rows
    by id, exactly like SignalEvidence/RecommendationEvidence in M2.
    Deliberately does NOT reference RawDocument or any Research-provider
    concept: Research owns raw evidence, Personalization owns strategy
    evidence, and the two are never mixed. At least one of signal_id/
    recommendation_id/intelligence_snapshot_id should be set (enforced at
    the application layer, not a DB constraint, to allow future evidence
    sources without a migration).
    """

    __tablename__ = "personalization_evidence"

    personalization_strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personalization_strategies.id", ondelete="CASCADE"), nullable=False, index=True
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

    personalization_strategy: Mapped["PersonalizationStrategy"] = relationship(back_populates="evidence")
    signal: Mapped["Signal | None"] = relationship()
    recommendation: Mapped["Recommendation | None"] = relationship()
    intelligence_snapshot: Mapped["IntelligenceSnapshot | None"] = relationship()
