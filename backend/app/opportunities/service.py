"""
Opportunity service - Track C3 (dashboard-capabilities-architecture-plan.md,
Section 1). The only module that writes Opportunity/OpportunityStageHistory
rows - mirrors app.crm_automation.service's "service is the only writer,
routes/frontend never touch the model directly" boundary.
app/api/routes/opportunities.py is the only caller of advance_stage; its
own PATCH endpoint deliberately never accepts a `stage` field (see that
route's own docstring) so every stage change is guaranteed to produce an
OpportunityStageHistory row, never a silent update.

M2 Phase 1c adds import_prospect_to_opportunity() - the "Prospect ->
Opportunity Import" action. It is deliberately a thin wrapper around the
EXISTING create_opportunity() above (never a second, parallel writer of
Opportunity rows) - this is what "reuse existing Opportunity/Contact/
Timeline patterns wherever possible" means concretely here: Opportunity
already keyed off prospect_id directly since Track C3 (never the legacy
Company/Contact tables), so importing a Prospect needs no new model, no
migration, and no second code path that could drift from create_opportunity's
own stage-history-writing guarantee.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import OpportunityStage, ProspectStatus
from app.models.opportunity import Opportunity
from app.models.opportunity_stage_history import OpportunityStageHistory
from app.models.prospect import Prospect
from app.models.prospect_timeline_event import ProspectTimelineEvent
from app.opportunities.state_machine import plan_stage_transition


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProspectNotApprovedError(ValueError):
    """M2 Phase 1c. Raised by import_prospect_to_opportunity() when the
    given Prospect's status isn't APPROVED - app.api.routes.prospects
    translates this into a 400. Mirrors
    app.opportunities.state_machine.InvalidStageTransitionError's own
    "domain module raises a specific exception, the route translates it"
    shape. APPROVED (not QUALIFIED) is the deliberate gate here - it's
    the literal language Prospect's own model docstring has used since
    M1: "until a future milestone's explicit, one-way import action
    creates a Company from an APPROVED Prospect." A QUALIFIED-but-not-
    yet-human-reviewed Prospect has passed automatic scoring, not a
    person's judgment call - Import is that second, human gate, turning
    a review decision into a real sales-pipeline record."""


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


def import_prospect_to_opportunity(
    db: Session,
    *,
    company_profile_id: uuid.UUID,
    prospect: Prospect,
    name: str | None = None,
    prospect_contact_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    **extra_fields,
) -> tuple[Opportunity, bool]:
    """M2 Phase 1c - "Prospect -> Opportunity Import".

    Idempotent: if an Opportunity already exists for this
    (company_profile_id, prospect_id) pair, returns that EXISTING row
    unchanged (bool=False) rather than creating a second one - "multiple
    imports must never create duplicate Opportunities" is enforced here,
    by query, not by a database uniqueness constraint (see the Phase 1c
    migration's own docstring for why a hard UNIQUE(prospect_id) would
    foreclose a legitimate future case: a second deal with a repeat
    customer after their first Opportunity already closed).

    Gated on prospect.status == APPROVED (see ProspectNotApprovedError's
    own docstring for why APPROVED specifically). Multi-business
    isolation is the caller's responsibility, exactly like every other
    Prospect-scoped route in this codebase: the caller must have already
    resolved `prospect` through get_owned_company_profile + a
    company_profile_id-scoped lookup (app.api.routes.prospects.
    _get_prospect_or_404) before this function ever sees it - this
    function only re-uses that already-validated company_profile_id, it
    does not re-check prospect.company_profile_id itself.

    On a genuine (non-idempotent-replay) import, writes exactly one
    ProspectTimelineEvent (event_type="imported_to_opportunity") - full
    audit/history, same append-only pattern every other Prospect
    lifecycle action (approve/reject/archive) already uses. An idempotent
    replay writes nothing new - the one real creation is what's on
    record, not every subsequent no-op check."""
    if prospect.status != ProspectStatus.APPROVED:
        raise ProspectNotApprovedError(
            f"Only APPROVED prospects can be imported into an Opportunity. Current status: '{prospect.status.value}'."
        )

    existing = db.scalars(
        select(Opportunity).where(
            Opportunity.company_profile_id == company_profile_id,
            Opportunity.prospect_id == prospect.id,
        )
    ).first()
    if existing is not None:
        return existing, False

    opportunity = create_opportunity(
        db,
        company_profile_id=company_profile_id,
        prospect_id=prospect.id,
        name=name or prospect.name,
        prospect_contact_id=prospect_contact_id,
        **extra_fields,
    )

    db.add(ProspectTimelineEvent(
        prospect_id=prospect.id,
        event_type="imported_to_opportunity",
        actor=f"user:{actor_user_id}" if actor_user_id else "system",
        payload={"opportunity_id": str(opportunity.id)},
    ))
    db.commit()
    db.refresh(opportunity)
    return opportunity, True


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
