import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import BuyerReadinessLevel, PersonalizationScope, RelationshipStage


class PersonalizationSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    An immutable, point-in-time capture of "what's the best sales strategy
    for this prospect right now" - never edited after creation, exact same
    versioning discipline as IntelligenceSnapshot. version auto-increments
    per prospect; exactly one row per prospect has is_current=True.

    buyer_readiness is an AI PREDICTION, recalculated fresh every run - it
    lives here, natively, because each version genuinely re-derives it.
    relationship_stage_at_generation is different: it's a frozen COPY of
    Prospect.relationship_stage (actual sales history, a live mutable
    field owned by future M4-M7 outreach systems) taken at generation
    time, purely for explainability ("the strategy assumed COLD, but the
    live value has since moved to CONTACTED"). This snapshot never writes
    Prospect.relationship_stage - only Prospect itself is the source of
    truth for that field.

    personalization_variables is a derived, regenerable projection (never
    hand-authored, same idea as ResearchReport.content) shaped as:
    {"company": str, "industry": str, "country": str, "buyer": str,
     "position": str, "communication_strategy": {...}, "buyer_readiness": str,
     "strategies": {"primary": {"signal", "pain_point", "recommendation", "cta"},
                     "secondary": {...}, "fallback": {...}}}
    Every value in it traces back to a real column/relationship elsewhere
    in this snapshot or its evidence - it exists so M4 can consume
    {{company}}/{{signal}}/{{cta}}/... directly instead of rebuilding
    context from the relational data itself.

    Holds only the AI's descriptive+predictive read of the buyer
    (persona, readiness) plus the variable projection. The actual
    prescriptive output - the ranked strategies themselves - lives in the
    child PersonalizationStrategy rows, not here, because there can be
    more than one (primary/secondary/fallback).

    scope: added for M4. Every M3/M4 pipeline run still only ever produces
    ACCOUNT-scoped snapshots (one strategy read per Prospect, regardless of
    which named ProspectContact ends up addressed) - CONTACT exists purely
    so a future per-stakeholder personalization upgrade is a new value, not
    a new column. Outreach (M4) addresses drafts per-ProspectContact but
    still reads the one current ACCOUNT-scoped snapshot for that prospect;
    this is a disclosed, deliberate simplification, not an oversight.
    """

    __tablename__ = "personalization_snapshots"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    personalization_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personalization_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    buyer_persona: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    buyer_readiness: Mapped[BuyerReadinessLevel] = mapped_column(
        Enum(
            BuyerReadinessLevel,
            name="buyer_readiness_level",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=BuyerReadinessLevel.UNKNOWN,
        nullable=False,
        index=True,
    )
    buyer_readiness_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    relationship_stage_at_generation: Mapped[RelationshipStage] = mapped_column(
        Enum(
            RelationshipStage,
            name="relationship_stage",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    personalization_variables: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    scope: Mapped[PersonalizationScope] = mapped_column(
        Enum(
            PersonalizationScope,
            name="personalization_scope",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=PersonalizationScope.ACCOUNT,
        nullable=False,
        index=True,
    )

    prospect: Mapped["Prospect"] = relationship()
    personalization_job: Mapped["PersonalizationJob | None"] = relationship()
    communication_strategy: Mapped["CommunicationStrategy | None"] = relationship(
        back_populates="personalization_snapshot", uselist=False, cascade="all, delete-orphan"
    )
    strategies: Mapped[list["PersonalizationStrategy"]] = relationship(
        back_populates="personalization_snapshot", cascade="all, delete-orphan"
    )
