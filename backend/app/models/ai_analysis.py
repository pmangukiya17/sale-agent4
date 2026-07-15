import uuid

from sqlalchemy import Enum, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AIAnalysisType
from app.models.research_associations import ai_analysis_source_documents


class AIAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One analysis pass over a batch of RawDocuments, scoped to exactly one
    AIAnalysisType. Kept as a single physical table across all four types
    (rather than four near-identical tables) because the execution
    metadata (research_job_id, model_used, prompt_version, raw_model_output,
    confidence, reasoning, token_usage) is identical across categories -
    only structured_output's shape differs, and that's validated by a
    per-type Pydantic schema at the API layer, not the DB layer.

    model_used/prompt_version exist so a real LLM can replace the
    deterministic stub later as a new AIAnalysisEngine implementation,
    with zero schema change - this table doesn't know or care which
    engine produced a row.
    """

    __tablename__ = "ai_analyses"

    research_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_type: Mapped[AIAnalysisType] = mapped_column(
        Enum(
            AIAnalysisType,
            name="ai_analysis_type",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    model_used: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_model_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    structured_output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_cost: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)

    research_job: Mapped["ResearchJob"] = relationship(back_populates="analyses")
    source_documents: Mapped[list["RawDocument"]] = relationship(secondary=ai_analysis_source_documents)
