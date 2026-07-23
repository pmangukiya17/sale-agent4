"""
Opportunity service - Track C3 (dashboard-capabilities-architecture-plan.md,
Section 1). The only module that writes Opportunity/OpportunityStageHistory
rows - mirrors app.crm_automation.service's "service is the only writer,
routes/frontend never touch the model directly" boundary.
app/api/routes/opportunities.py is the only caller of advance_stage; its
own PATCH endpoint deliberately never accepts a `stage` field (see that
route's own docstring) so every stage change is guaranteed to produce an
OpportunityStageHistory row, never a silent update.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import OpportunityStage
from app.models.opportunity import Opportunity
from app.models.opportunity_stage_history import OpportunityStageHistory
from app.opportunities.state_machine import plan_stage_transition


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_opportunity(
    db: Session,
    *,
    company_profile_id: uuid.UUID,
    prospect_id: uuid.UUID,
    name: str,
    prospect_contact_id: uuid.UUID | None = None,
    stage: OpportunityStage = OpportunityStage.QUALIFIED_LEAD,
    **extra_fields,
) -> Opportunity:
    """Creates an Opportunity and its one initial OpportunityStageHistory
    row (from_stage=None, to_stage=the starting stage) - every
    Opportunity's complete stage history, including creation, lives in
    one table from day one, per this track's own analytics-from-history
    design decision."""
    opportunity = Opportunity(
        company_profile_id=company_profile_id,
        prospect_id=prospect_id,
        prospect_contact_id=prospect_contact_id,
        name=name,
        stage=stage,
        **extra_fields,
    )
    db.add(opportunity)
    db.flush()  # need opportunity.id for the history row below

    db.add(
        OpportunityStageHistory(
            opportunity_id=opportunity.id,
            from_stage=None,
            to_stage=stage,
            changed_at=_now(),
        )
    )
    db.commit()
    db.refresh(opportunity)
    return opportunity


def advance_stage(
    db: Session,
    opportunity: Opportunity,
    to_stage: OpportunityStage,
    *,
    changed_by_user_id: uuid.UUID | None = None,
    lost_reason: str | None = None,
) -> Opportunity:
    """The only path that ever changes Opportunity.stage - always writes
    an OpportunityStageHistory row alongside it. Raises
    state_machine.InvalidStageTransitionError for a same-stage no-op;
    the route layer translates that into a 400. Sets closed_at whenever
    to_stage is a closed stage, clears it otherwise (including when
    re-opening a previously-closed deal) - deterministic, not dependent
    on the previous stage. lost_reason is only ever kept when the
    destination is CLOSED_LOST; any other transition clears a stale one
    rather than leaving it to describe a deal that isn't lost anymore."""
    transition = plan_stage_transition(opportunity.stage, to_stage)

    from_stage = opportunity.stage
    opportunity.stage = transition.to_stage
    opportunity.closed_at = _now() if transition.is_closed else None
    opportunity.lost_reason = lost_reason if transition.to_stage == OpportunityStage.CLOSED_LOST else None

    db.add(
        OpportunityStageHistory(
            opportunity_id=opportunity.id,
            from_stage=from_stage,
            to_stage=transition.to_stage,
            changed_by_user_id=changed_by_user_id,
            changed_at=_now(),
        )
    )
    db.commit()
    db.refresh(opportunity)
    return opportunity


def compute_funnel(db: Session, company_profile_id: uuid.UUID) -> list[dict]:
    """Pipeline Overview's own aggregation: one GROUP BY over the CURRENT
    stage distribution (COUNT(*) per stage), returned in the enum's
    declared order (not creation order) so the funnel always renders
    stage-by-stage, every stage present even at zero. Deliberately reads
    Opportunity.stage (current state), not OpportunityStageHistory - "how
    many deals are AT this stage right now" is a different question from
    "how many transitions into this stage have ever happened," and
    Pipeline Overview's funnel is the former. A future stage-duration/
    velocity report is exactly where OpportunityStageHistory's
    append-only record earns its keep - out of scope for this slice."""
    stmt = (
        select(Opportunity.stage, func.count())
        .where(Opportunity.company_profile_id == company_profile_id)
        .group_by(Opportunity.stage)
    )
    counts = {stage: count for stage, count in db.execute(stmt).all()}
    return [{"stage": stage.value, "count": counts.get(stage, 0)} for stage in OpportunityStage]


def compute_pipeline_value(db: Session, company_profile_id: uuid.UUID) -> dict:
    """Revenue Pipeline's own single-purpose read: SUM(estimated_revenue)
    over every OPEN (non-closed) Opportunity, plus a separate
    SUM(actual_revenue) over CLOSED_WON deals only - a distinct "won this
    period" figure, never folded into the open-pipeline total. A
    dedicated, cheap endpoint kept separate from compute_funnel's heavier
    full breakdown, so the KPI strip's own perf budget never depends on
    it."""
    open_stmt = select(func.coalesce(func.sum(Opportunity.estimated_revenue), 0)).where(
        Opportunity.company_profile_id == company_profile_id,
        Opportunity.stage.notin_([OpportunityStage.CLOSED_WON, OpportunityStage.CLOSED_LOST]),
    )
    won_stmt = select(func.coalesce(func.sum(Opportunity.actual_revenue), 0)).where(
        Opportunity.company_profile_id == company_profile_id,
        Opportunity.stage == OpportunityStage.CLOSED_WON,
    )
    open_pipeline_value = db.scalar(open_stmt)
    closed_won_value = db.scalar(won_stmt)
    return {
        "open_pipeline_value": float(open_pipeline_value or 0),
        "closed_won_value": float(closed_won_value or 0),
    }
