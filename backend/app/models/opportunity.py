import uuid
from datetime import date, datetime

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OpportunityForecastCategory, OpportunityStage


class Opportunity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Track C3 (dashboard-capabilities-architecture-plan.md, Section 1): the
    platform's first real, monetary sales-deal record. A genuinely new
    axis, deliberately distinct from two existing-but-similar-looking
    concepts already on Prospect: RelationshipStage ("how warmed up is
    this account," advanced by app.crm_automation.state_machine) and
    ProspectStatus ("where is this row in Discovery->Qualification").
    Opportunity answers a third question neither of those does - "is
    there a monetary deal, and where is it in the deal-stage funnel."

    stage MAY skip values and is NOT enforced as a linear progression -
    the CEO's explicit final design decision for this track. Every stage
    change (including creation) is written to OpportunityStageHistory by
    app.opportunities.service.advance_stage - never by this route/model
    directly - so reporting/analytics are always derived from the
    recorded history, never an assumed path through the enum's order.

    AI-ready from day one per the CEO's explicit direction: ai_confidence
    _score, win_probability, forecast_category, ai_reasoning, and
    next_recommended_action all exist as real, nullable columns starting
    now even though no AI engine populates them yet - the same
    "additive, not a schema fight" bet OutreachContext/Task.assigned_user_id
    already made for their own future milestones (see this table's own
    Section 1.7/1.8 in the architecture doc). Nothing here is fabricated:
    every one of these fields is genuinely NULL until a real value exists.

    estimated_revenue/actual_revenue are separate columns (not one
    "amount" field, per the CEO's own wording) - estimated_revenue is the
    deal's current worth estimate at any stage; actual_revenue is only
    ever meaningful once a deal is CLOSED_WON, and is never auto-derived
    from estimated_revenue (an honest, deliberately manual entry - this
    review does not invent a revenue-recognition rule the CEO hasn't
    specified). Both NUMERIC(14,2), not Float, since this is real money -
    unlike Prospect.total_score/Company.legitimacy_score, which are
    legitimately approximate AI scores, currency rounding error here
    would be a genuine correctness bug.

    Never touches RelationshipStage or ProspectStatus - both stay exactly
    what they already are.
    """

    __tablename__ = "opportunities"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prospect_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospect_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[OpportunityStage] = mapped_column(
        Enum(
            OpportunityStage,
            name="opportunity_stage",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=OpportunityStage.QUALIFIED_LEAD,
        nullable=False,
        index=True,
    )

    # Real money - NUMERIC, not Float. See this model's own docstring.
    estimated_revenue: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    actual_revenue: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)  # ISO 4217, e.g. "USD"

    # AI-ready fields (CEO's explicit direction) - real columns, genuinely
    # NULL until a future AI engine populates them. win_probability and
    # ai_confidence_score are deliberately two separate 0-100 floats: the
    # former is "how likely is this deal to close," the latter is "how
    # confident is the AI in its own read of this opportunity" - two
    # different questions that happen to share a scale, same
    # two-axes-that-look-similar-but-answer-different-questions
    # reasoning BuyerReadinessLevel vs RelationshipStage already
    # documents in app/models/enums.py.
    win_probability: Mapped[float | None] = mapped_column(nullable=True)
    ai_confidence_score: Mapped[float | None] = mapped_column(nullable=True)
    forecast_category: Mapped[OpportunityForecastCategory | None] = mapped_column(
        Enum(
            OpportunityForecastCategory,
            name="opportunity_forecast_category",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
        index=True,
    )
    ai_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Plain text for now, same shape as Task.suggested_action - no AI
    # engine writes this yet; exists so a future one can without a
    # migration.
    next_recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Opportunity owner - anticipatory but real: nullable, unenforced
    # multi-user assignment, same "future M9 Organization & AI Workforce
    # Management field, unused by any rule today" bet Task.assigned_user_id
    # already made.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Provenance - mirrors Task.source_event_type's honesty about where a
    # row came from, when it came from a deterministic system trigger
    # rather than a direct user action.
    source_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )

    company_profile: Mapped["CompanyProfile"] = relationship()
    prospect: Mapped["Prospect"] = relationship()
    prospect_contact: Mapped["ProspectContact | None"] = relationship()
    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_user_id])
    source_task: Mapped["Task | None"] = relationship(foreign_keys=[source_task_id])
    stage_history: Mapped[list["OpportunityStageHistory"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan", order_by="OpportunityStageHistory.changed_at"
    )
