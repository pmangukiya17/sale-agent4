import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RecommendationEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Same shape and rationale as SignalEvidence, for Recommendation."""

    __tablename__ = "recommendation_evidence"

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ai_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_analyses.id", ondelete="SET NULL"), nullable=True
    )
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    recommendation: Mapped["Recommendation"] = relationship(back_populates="evidence")
    raw_document: Mapped["RawDocument"] = relationship()
    ai_analysis: Mapped["AIAnalysis | None"] = relationship()
