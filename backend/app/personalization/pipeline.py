"""
Personalization pipeline orchestrator - structural mirror of Discovery's
(M1) and Research's (M2) pipelines, minus the provider-fan-out layer:
Personalization fetches nothing external, it only reads what M1/M2
already stored and synthesizes a strategy in one internal engine call.

This pipeline never writes Prospect.ai_reasoning (that field is M2's) and
never writes Prospect.relationship_stage (that field is live, mutable,
and owned by future M4-M7 outreach systems) - it only ever READS
relationship_stage, copying it into
PersonalizationSnapshot.relationship_stage_at_generation for
explainability.

M8.14 update: same treatment Discovery (M8.8) and Research (M8.13) got -
this function is now ALSO reachable asynchronously via
PersonalizationExecutionAction (app/workflow_actions/
personalization_execution_action.py), triggered off a real Event through
the M7 Workflow Engine, in addition to the still-supported synchronous
/run route. Unlike Discovery/Research, there is no provider fan-out to
report incremental progress on - a personalization run is genuinely one
atomic synthesis step, so there are only two real transitions to publish:
job created (RUNNING) and job terminal (COMPLETED/FAILED). Publishing a
fake "halfway" event here would be exactly the fabricated-progress
Principle 1 forbids - this pipeline does not invent one just to have more
than two events.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.communication_strategy import CommunicationStrategy
from app.models.enums import PersonalizationJobStatus, ProductStatus, RecommendationStatus, SignalStatus
from app.models.icp_criteria import ICPCriteria
from app.models.intelligence_snapshot import IntelligenceSnapshot
from app.models.knowledge_base import KnowledgeBase
from app.models.personalization_evidence import PersonalizationEvidence
from app.models.personalization_job import PersonalizationJob
from app.models.personalization_request import PersonalizationRequest
from app.models.personalization_run import PersonalizationRun
from app.models.personalization_snapshot import PersonalizationSnapshot
from app.models.personalization_strategy import PersonalizationStrategy
from app.models.product import Product
from app.models.prospect import Prospect
from app.models.recommendation import Recommendation
from app.models.signal import Signal
from app.models.user import User
from app.personalization.context import PersonalizationContext
from app.personalization.engine.base import PersonalizationOutcome, StrategyDraft
from app.personalization.engine.deterministic_stub import DeterministicPersonalizationEngine
from app.workflow_engine.events import publish_event

# M8.14: the two Personalization event types - exact mirror of
# DISCOVERY_SEARCH_RUN_REQUESTED_EVENT_TYPE / DISCOVERY_JOB_PROGRESS_EVENT_TYPE.
PERSONALIZATION_REQUEST_RUN_REQUESTED_EVENT_TYPE = "personalization_request.run_requested"
PERSONALIZATION_JOB_PROGRESS_EVENT_TYPE = "personalization_job.progress"


def _publish_job_progress(db: Session, job: PersonalizationJob, company_profile_id) -> None:
    publish_event(
        db,
        event_type=PERSONALIZATION_JOB_PROGRESS_EVENT_TYPE,
        company_profile_id=company_profile_id,
        source="app.personalization.pipeline",
        subject_type="personalization_job",
        subject_id=job.id,
        payload={"status": job.status.value if hasattr(job.status, "value") else job.status},
    )

# Maps a Recommendation's type onto which {{...}} variable slot it fills -
# see PersonalizationSnapshot's docstring for the personalization_variables
# shape this feeds.
_RECOMMENDATION_TYPE_TO_SLOT = {
    "product_fit": "recommendation",
    "sales_angle": "recommendation",
    "talking_point": "pain_point",
    "objection_handling": "pain_point",
    "risk_mitigation": "pain_point",
    "call_to_action": "cta",
}


class PersonalizationConfigError(Exception):
    """Raised when a personalization job can't run because of missing
    configuration - a 400, not a 500."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_context(db: Session, prospect: Prospect) -> PersonalizationContext:
    company_profile = prospect.company_profile

    snapshot_stmt = select(IntelligenceSnapshot).where(
        IntelligenceSnapshot.prospect_id == prospect.id, IntelligenceSnapshot.is_current.is_(True)
    )
    intelligence_snapshot = db.scalars(snapshot_stmt).first()

    signals = list(
        db.scalars(
            select(Signal).where(Signal.prospect_id == prospect.id, Signal.status != SignalStatus.DISMISSED)
        ).all()
    )
    recommendations = list(
        db.scalars(
            select(Recommendation).where(
                Recommendation.prospect_id == prospect.id, Recommendation.status != RecommendationStatus.DISMISSED
            )
        ).all()
    )
    products = list(
        db.scalars(
            select(Product).where(Product.company_profile_id == company_profile.id, Product.status == ProductStatus.ACTIVE)
        ).all()
    )
    icp = db.scalars(
        select(ICPCriteria).where(ICPCriteria.company_profile_id == company_profile.id, ICPCriteria.is_active.is_(True))
    ).first()
    kb_entries = list(
        db.scalars(select(KnowledgeBase).where(KnowledgeBase.company_profile_id == company_profile.id)).all()
    )

    return PersonalizationContext(
        prospect=prospect,
        company_profile=company_profile,
        intelligence_snapshot=intelligence_snapshot,
        signals=signals,
        recommendations=recommendations,
        products=products,
        icp=icp,
        knowledge_base_entries=kb_entries,
    )


def _next_snapshot_version(db: Session, prospect_id) -> int:
    return (
        db.scalar(select(func.coalesce(func.max(PersonalizationSnapshot.version), 0)).where(PersonalizationSnapshot.prospect_id == prospect_id))
        + 1
    )


def _unset_previous_current_snapshot(db: Session, prospect_id) -> None:
    stmt = select(PersonalizationSnapshot).where(
        PersonalizationSnapshot.prospect_id == prospect_id, PersonalizationSnapshot.is_current.is_(True)
    )
    for snapshot in db.scalars(stmt).all():
        snapshot.is_current = False


def _strategy_variable_slots(strategy: StrategyDraft, recommendations_by_id: dict, signals_by_id: dict) -> dict:
    slots = {"signal": None, "pain_point": None, "recommendation": None, "cta": None}
    for ev in strategy.evidence:
        if ev.signal_id is not None and ev.signal_id in signals_by_id:
            slots["signal"] = signals_by_id[ev.signal_id].title
        if ev.recommendation_id is not None and ev.recommendation_id in recommendations_by_id:
            rec = recommendations_by_id[ev.recommendation_id]
            slot_name = _RECOMMENDATION_TYPE_TO_SLOT.get(rec.recommendation_type.value, "recommendation")
            slots[slot_name] = rec.title
    return slots


def _build_personalization_variables(
    context: PersonalizationContext, outcome: PersonalizationOutcome, strategies_by_rank: dict
) -> dict:
    prospect = context.prospect
    top_contact = prospect.contacts[0] if getattr(prospect, "contacts", None) else None
    recommendations_by_id = {r.id: r for r in context.recommendations}
    signals_by_id = {s.id: s for s in context.signals}

    comm = outcome.communication_strategy
    return {
        "company": context.company_profile.name,
        "industry": prospect.industry_raw,
        "country": prospect.country,
        "buyer": prospect.name,
        "position": top_contact.role if top_contact else None,
        "communication_strategy": {
            "formality": comm.formality.value,
            "directness": comm.directness.value,
            "warmth": comm.warmth.value,
            "technical_depth": comm.technical_depth.value,
            "authority": comm.authority.value,
            "consultative_level": comm.consultative_level.value,
            "urgency": comm.urgency.value,
            "message_length": comm.message_length.value,
        },
        "buyer_readiness": outcome.buyer_readiness.value,
        "strategies": {
            rank.value: _strategy_variable_slots(draft, recommendations_by_id, signals_by_id)
            for rank, draft in strategies_by_rank.items()
        },
    }


def run_personalization_request(
    db: Session,
    request: PersonalizationRequest,
    triggered_by_user: User,
) -> PersonalizationJob:
    prospect = db.get(Prospect, request.prospect_id)
    context = _build_context(db, prospect)

    job = PersonalizationJob(
        personalization_request_id=request.id,
        prospect_id=request.prospect_id,
        company_profile_id=request.company_profile_id,
        status=PersonalizationJobStatus.RUNNING,
        started_at=_now(),
    )
    db.add(job)
    db.flush()  # need job.id before child rows reference it

    # M8.14: commit + publish immediately, before the synthesis engine has
    # even run - a live viewer polling this job sees it exist and be
    # RUNNING right away (see app.discovery.pipeline's identical precedent).
    _publish_job_progress(db, job, request.company_profile_id)
    db.commit()
    db.refresh(job)

    job_log: list[dict] = []
    error_message: str | None = None

    try:
        engine = DeterministicPersonalizationEngine()
        outcome = engine.synthesize(context)
        job_log.append({"engine": outcome.model_used, "prompt_version": outcome.prompt_version, "status": "completed"})
    except Exception as exc:  # noqa: BLE001 - a genuine engine failure, not "nothing found"
        error_message = str(exc)
        job_log.append({"status": "failed", "error": error_message})
        job.status = PersonalizationJobStatus.FAILED
        job.finished_at = _now()
        job.error_message = error_message
        job.log = job_log
        request.status = job.status
        _publish_job_progress(db, job, request.company_profile_id)
        db.commit()
        db.refresh(job)
        return job

    # --- PersonalizationSnapshot: new version, unset the previous current --
    _unset_previous_current_snapshot(db, request.prospect_id)
    next_version = _next_snapshot_version(db, request.prospect_id)

    snapshot = PersonalizationSnapshot(
        prospect_id=request.prospect_id,
        version=next_version,
        personalization_job_id=job.id,
        company_profile_id=request.company_profile_id,
        is_current=True,
        buyer_persona=outcome.buyer_persona,
        buyer_readiness=outcome.buyer_readiness,
        buyer_readiness_reasoning=outcome.buyer_readiness_reasoning,
        relationship_stage_at_generation=prospect.relationship_stage,
    )
    db.add(snapshot)
    db.flush()  # need snapshot.id for child rows

    db.add(CommunicationStrategy(
        personalization_snapshot_id=snapshot.id,
        formality=outcome.communication_strategy.formality,
        directness=outcome.communication_strategy.directness,
        warmth=outcome.communication_strategy.warmth,
        technical_depth=outcome.communication_strategy.technical_depth,
        authority=outcome.communication_strategy.authority,
        consultative_level=outcome.communication_strategy.consultative_level,
        urgency=outcome.communication_strategy.urgency,
        message_length=outcome.communication_strategy.message_length,
        rationale=outcome.communication_strategy.rationale,
    ))

    strategies_by_rank = {}
    for draft in outcome.strategies:
        strategy = PersonalizationStrategy(
            personalization_snapshot_id=snapshot.id,
            strategy_rank=draft.strategy_rank,
            title=draft.title,
            narrative=draft.narrative,
            confidence=draft.confidence,
            reasoning=draft.reasoning,
        )
        db.add(strategy)
        db.flush()  # need strategy.id for evidence rows
        for ev in draft.evidence:
            db.add(PersonalizationEvidence(
                personalization_strategy_id=strategy.id,
                signal_id=ev.signal_id,
                recommendation_id=ev.recommendation_id,
                intelligence_snapshot_id=ev.intelligence_snapshot_id,
                excerpt=ev.excerpt,
            ))
        strategies_by_rank[draft.strategy_rank] = draft

    snapshot.personalization_variables = _build_personalization_variables(context, outcome, strategies_by_rank)

    job.finished_at = _now()
    job.status = PersonalizationJobStatus.COMPLETED
    job.error_message = None
    job.log = job_log
    job.strategy_count = len(outcome.strategies)
    request.status = job.status

    run = PersonalizationRun(
        personalization_request_id=request.id,
        personalization_job_id=job.id,
        prospect_id=request.prospect_id,
        company_profile_id=request.company_profile_id,
        triggered_by_user_id=triggered_by_user.id,
        triggered_at=job.started_at,
        config_snapshot={
            "personalization_template_id": str(request.personalization_template_id),
            "personalization_template_name": request.personalization_template.name,
            "intelligence_snapshot_id": str(context.intelligence_snapshot.id) if context.intelligence_snapshot else None,
            "intelligence_snapshot_version": context.intelligence_snapshot.version if context.intelligence_snapshot else None,
            "signal_ids": [str(s.id) for s in context.signals],
            "recommendation_ids": [str(r.id) for r in context.recommendations],
            "icp_criteria_id": str(context.icp.id) if context.icp else None,
            "icp_version": context.icp.version if context.icp else None,
        },
        personalization_version_created=next_version,
    )
    db.add(run)

    # M8.14: the final transition - one last nudge so a live viewer knows
    # to fetch the completion summary.
    _publish_job_progress(db, job, request.company_profile_id)
    db.commit()
    db.refresh(job)
    return job
