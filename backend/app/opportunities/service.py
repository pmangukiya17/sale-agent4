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


# Track C4 (dashboard-capabilities-architecture-plan.md, Sections 2-4):
# the sequential conversion chain Pipeline Overview's funnel walks
# stage-to-stage. CLOSED_LOST is deliberately excluded from this
# sequence and reported separately (see compute_funnel's own docstring)
# - it is a drop-off OUTCOME that can happen from any open stage, not a
# step every deal sequentially passes through, so "conversion rate from
# CLOSED_WON to CLOSED_LOST" (what including it in enum order would
# produce) is not a meaningful number.
_FUNNEL_SEQUENCE = (
    OpportunityStage.QUALIFIED_LEAD,
    OpportunityStage.MEETING,
    OpportunityStage.SAMPLE,
    OpportunityStage.QUOTATION,
    OpportunityStage.NEGOTIATION,
    OpportunityStage.PURCHASE_ORDER,
    OpportunityStage.CLOSED_WON,
)


def compute_funnel(db: Session, company_profile_id: uuid.UUID) -> list[dict]:
    """Pipeline Overview's own aggregation: one GROUP BY over the CURRENT
    stage distribution (COUNT(*) per stage), every declared stage present
    even at zero. Deliberately reads Opportunity.stage (current state),
    not OpportunityStageHistory - "how many deals are AT this stage right
    now" is a different question from "how many transitions into this
    stage have ever happened," and Pipeline Overview's funnel is the
    former. A future stage-duration/velocity report is exactly where
    OpportunityStageHistory's append-only record earns its keep - out of
    scope for this slice.

    Each row also carries `conversion_rate_from_previous` (Track C4,
    Section 3.5's own "conversion-rate math lives here, not duplicated in
    two frontend components" requirement) - a lightweight, CURRENT-
    distribution-based approximation (this stage's count / the previous
    stage's count in _FUNNEL_SEQUENCE), not a cohort/historical
    conversion rate. Since stages MAY be skipped (Track C3's own design
    decision), a deal sitting at PURCHASE_ORDER right now may never have
    been counted at MEETING/SAMPLE/QUOTATION at all - this percentage
    describes today's relative distribution across stages, not "what
    fraction of deals that reached stage N ever reached stage N+1." A
    real cohort-based conversion rate would need to read
    OpportunityStageHistory instead - explicitly out of scope here, see
    Section 1.12's own deferral of stage-duration/velocity reporting.
    None for the first stage (no previous stage to divide by) and
    whenever the previous stage's count is 0 (avoids a division by zero
    masquerading as a real percentage). CLOSED_LOST is always None here -
    it's reported as a separate drop-off figure, not part of the
    sequential chain - see this module's own _FUNNEL_SEQUENCE comment."""
    stmt = (
        select(Opportunity.stage, func.count())
        .where(Opportunity.company_profile_id == company_profile_id)
        .group_by(Opportunity.stage)
    )
    counts = {stage: count for stage, count in db.execute(stmt).all()}

    rows: list[dict] = []
    previous_count: int | None = None
    for stage in _FUNNEL_SEQUENCE:
        count = counts.get(stage, 0)
        conversion_rate = None
        if previous_count is not None and previous_count > 0:
            conversion_rate = round((count / previous_count) * 100, 1)
        rows.append({"stage": stage.value, "count": count, "conversion_rate_from_previous": conversion_rate})
        previous_count = count

    rows.append(
        {
            "stage": OpportunityStage.CLOSED_LOST.value,
            "count": counts.get(OpportunityStage.CLOSED_LOST, 0),
            "conversion_rate_from_previous": None,
        }
    )
    return rows


def compute_pipeline_value(db: Session, company_profile_id: uuid.UUID) -> list[dict]:
    """Revenue Pipeline's own read: SUM(estimated_revenue) over every OPEN
    (non-closed) Opportunity, plus a separate SUM(actual_revenue) over
    CLOSED_WON deals only - two distinct figures, never folded together.

    Track C4 fix (resolves Section 4.10's explicitly-deferred decision,
    now that Revenue Pipeline is the exact track that renders this number
    to a human): grouped BY CURRENCY rather than one blind SUM across
    every Opportunity regardless of `currency`. Section 4.10's own words:
    "SUM(amount) across [mixed currencies] is meaningless without
    conversion" - so this returns one row per distinct currency actually
    in use (including a `None`/"unspecified" bucket for Opportunities with
    no currency set) rather than ever silently blending them into one
    number. In the common single-currency-business case this is exactly
    one row - the KPI card renders that as its single headline number;
    a business with genuinely mixed currencies gets an honest breakdown
    instead of a nonsense total. Empty pipeline (no Opportunities at all)
    returns an empty list - the widget's own "no pipeline data yet" case,
    not a fabricated zero-value row for a currency nothing uses."""
    open_stmt = (
        select(Opportunity.currency, func.coalesce(func.sum(Opportunity.estimated_revenue), 0))
        .where(
            Opportunity.company_profile_id == company_profile_id,
            Opportunity.stage.notin_([OpportunityStage.CLOSED_WON, OpportunityStage.CLOSED_LOST]),
        )
        .group_by(Opportunity.currency)
    )
    won_stmt = (
        select(Opportunity.currency, func.coalesce(func.sum(Opportunity.actual_revenue), 0))
        .where(
            Opportunity.company_profile_id == company_profile_id,
            Opportunity.stage == OpportunityStage.CLOSED_WON,
        )
        .group_by(Opportunity.currency)
    )
    open_by_currency = dict(db.execute(open_stmt).all())
    won_by_currency = dict(db.execute(won_stmt).all())

    currencies = set(open_by_currency) | set(won_by_currency)
    return [
        {
            "currency": currency,
            "open_pipeline_value": float(open_by_currency.get(currency, 0) or 0),
            "closed_won_value": float(won_by_currency.get(currency, 0) or 0),
        }
        # None (no currency set) sorts last, real currency codes sort alphabetically.
        for currency in sorted(currencies, key=lambda c: (c is None, c))
    ]
