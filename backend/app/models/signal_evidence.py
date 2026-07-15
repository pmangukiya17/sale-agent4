import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SignalEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Real referential integrity for "every AI conclusion should contain
    source references" - a proper table (not a JSONB list) so each piece
    of evidence backing a Signal is individually queryable/audit-able
    ("show me every signal this raw document contributed to").
    """

    __tablename__ = "signal_evidence"

    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ai_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_analyses.id", ondelete="SET NULL"), nullable=True
    )
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    signal: Mapped["Signal"] = relationship(back_populates="evidence")
    raw_document: Mapped["RawDocument"] = relationship()
    ai_analysis: Mapped["AIAnalysis | None"] = relationship()
