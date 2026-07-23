import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OpportunityStage


class OpportunityStageHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Track C3 (dashboard-capabilities-architecture-plan.md, Section 1):
    append-only stage-transition log for one Opportunity - never mutated
    after creation, same discipline as OutreachEdit/ProspectTimelineEvent.
    Written exclusively by app.opportunities.service.advance_stage (and
    once, at creation, for the initial stage) - never directly by a route
    or the frontend.

    This table is the actual authority for every stage-based report
    (Pipeline Overview's funnel, conversion rates, stage-duration
    analytics): per the CEO's explicit direction, an Opportunity MAY skip
    stages and this platform does NOT enforce a linear workflow, so any
    reporting logic that assumed "every deal passes through every stage
    in order" would be silently wrong. Every transition, including
    skipped ones, is a real row here - see
    app.opportunities.service.compute_funnel for the read side of that
    same discipline.

    from_stage is NULL only for the single row created at Opportunity
    creation (there is no "previous stage" for a brand-new deal).
    """

    __tablename__ = "opportunity_stage_history"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_stage: Mapped[OpportunityStage | None] = mapped_column(
        Enum(
            OpportunityStage,
            name="opportunity_stage",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )
    to_stage: Mapped[OpportunityStage] = mapped_column(
        Enum(
            OpportunityStage,
            name="opportunity_stage",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(nullable=False)

    opportunity: Mapped["Opportunity"] = relationship(back_populates="stage_history")
