"""
Research pipeline orchestrator - exact structural mirror of Discovery's
pipeline.py (M1), extended with an AI Analysis pass.

One deliberate, disclosed adaptation vs. Discovery: DiscoverySearch is a
reusable saved config with its own persisted query_spec column, so its
`/run` endpoint takes no body. ResearchRequest is explicitly NOT a
reusable saved config (see research_request.py docstring) - it is a
one-off "research this prospect" per-run intent - so it has no
persisted source_spec column of its own. The per-run input documents
(what the manual_document provider will read) are therefore supplied at
run time via `run_input`, merged on top of the ResearchTemplate's
research_spec the exact same way DiscoverySearch merges its own
query_spec on top of its SearchTemplate's: `{**template_spec,
**run_input}`. The merged dict is never persisted on ResearchRequest
itself - only its effects (RawDocuments, ResearchRun.config_snapshot)
are, preserving the "per-run, not reusable" intent.

M8.13 update: same treatment as Discovery got in M8.8 - this function is
now ALSO reachable asynchronously via ResearchExecutionAction
(app/workflow_actions/research_execution_action.py), triggered off a real
Event through the M7 Workflow Engine, in addition to the still-supported
synchronous /run route. To make the async path produce genuinely live,
incremental progress, this function commits at multiple points instead of
one (job created -> each provider as it finishes -> final, after the AI
Analysis pass), each paired with a real
publish_event(RESEARCH_JOB_PROGRESS_EVENT_TYPE) - identical shape to
DISCOVERY_JOB_PROGRESS_EVENT_TYPE, see that module's own docstring for the
full reasoning. The synchronous /run route no longer calls this directly
(see app/api/routes/research_requests.py) - it publishes
RESEARCH_REQUEST_RUN_REQUESTED_EVENT_TYPE instead - but this function's
own signature and every existing synchronous caller continue to work
unchanged; incremental commits are an internal implementation detail.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_analysis import AIAnalysis
from app.models.enums import (
    AIAnalysisType,
    RecommendationStatus,
    RecommendationType,
    ResearchJobStatus,
    SignalImportance,
    SignalStatus,
    SignalUrgency,
)
from app.models.intelligence_snapshot import IntelligenceSnapshot
from app.models.knowledge_base import KnowledgeBase
from app.models.product import Product
from app.models.prospect import Prospect
from app.models.raw_document import RawDocument
from app.models.recommendation import Recommendation
from app.models.recommendation_evidence import RecommendationEvidence
from app.models.research_job import ResearchJob
from app.models.research_job_provider_run import ResearchJobProviderRun
from app.models.research_request import ResearchRequest
from app.models.research_run import ResearchRun
from app.models.research_source import ResearchSource
from app.models.signal import Signal
from app.models.signal_evidence import SignalEvidence
from app.models.user import User
from app.research.analysis.base import AnalysisOutcome
from app.research.analysis.registry import get_analysis_engine
from app.research.context import ResearchContext
from app.research.providers.base import ProviderError
from app.research.providers.registry import get_provider
from app.workflow_engine.events import publish_event

# M8.13: the two Research event types the Live Workflow Visualization is
# built on - exact mirror of DISCOVERY_SEARCH_RUN_REQUESTED_EVENT_TYPE /
# DISCOVERY_JOB_PROGRESS_EVENT_TYPE (app/discovery/pipeline.py).
RESEARCH_REQUEST_RUN_REQUESTED_EVENT_TYPE = "research_request.run_requested"
RESEARCH_JOB_PROGRESS_EVENT_TYPE = "research_job.progress"


class ResearchConfigError(Exception):
    """Raised when a research job can't run because of missing
    configuration (unknown provider, ...) - a 400, not a 500."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_context(db: Session, prospect: Prospect) -> ResearchContext:
    company_profile = prospect.company_profile
    products = list(
        db.scalars(select(Product).where(Product.company_profile_id == company_profile.id)).all()
    )
    kb_entries = list(
        db.scalars(select(KnowledgeBase).where(KnowledgeBase.company_profile_id == company_profile.id)).all()
    )
    return ResearchContext(prospect=prospect, company_profile=company_profile, products=products, knowledge_base_entries=kb_entries)


def _merged_source_spec(request: ResearchRequest, run_input: dict | None) -> dict:
    template_spec = request.research_template.research_spec or {}
    return {**template_spec, **(run_input or {})}


def _next_snapshot_version(db: Session, prospect_id) -> int:
    return (
        db.scalar(select(func.coalesce(func.max(IntelligenceSnapshot.version), 0)).where(IntelligenceSnapshot.prospect_id == prospect_id))
        + 1
    )


def _unset_previous_current_snapshot(db: Session, prospect_id) -> None:
    stmt = select(IntelligenceSnapshot).where(
        IntelligenceSnapshot.prospect_id == prospect_id,
        IntelligenceSnapshot.is_current.is_(True),
    )
    for snapshot in db.scalars(stmt).all():
        snapshot.is_current = False


def _publish_job_progress(db: Session, job: ResearchJob, company_profile_id) -> None:
    """Mirrors app.discovery.pipeline._publish_job_progress exactly - a
    nudge, no payload beyond enough to identify the job. Flushes but does
    not commit; callers pair this with their own db.commit() immediately
    after."""
    publish_event(
        db,
        event_type=RESEARCH_JOB_PROGRESS_EVENT_TYPE,
        company_profile_id=company_profile_id,
        source="app.research.pipeline",
        subject_type="research_job",
        subject_id=job.id,
        payload={"status": job.status.value if hasattr(job.status, "value") else job.status},
    )


def run_research_request(
    db: Session,
    request: ResearchRequest,
    triggered_by_user: User,
    run_input: dict | None = None,
) -> ResearchJob:
    # M11 (AI Provider Hierarchy): premium_approved is a per-run AI-approval
    # decision, not document-source configuration - extracted here, before
    # merging the rest of run_input into source_spec, so it never leaks
    # into a research provider's own fetch() config dict. See
    # app/api/routes/research_requests.py's ai-preflight endpoint for
    # where a human actually makes this decision, and
    # ResearchRequestRunBody.premium_approved for how it arrives here via
    # the workflow event payload's run_input.
    premium_approved = bool((run_input or {}).get("premium_approved", False))
    run_input_for_sources = {k: v for k, v in (run_input or {}).items() if k != "premium_approved"} or None

    prospect = db.get(Prospect, request.prospect_id)
    context = _build_context(db, prospect)
    source_spec = _merged_source_spec(request, run_input_for_sources)
    provider_keys = source_spec.get("source_types") or ["manual_document"]

    job = ResearchJob(
        research_request_id=request.id,
        prospect_id=request.prospect_id,
        company_profile_id=request.company_profile_id,
        status=ResearchJobStatus.RUNNING,
        started_at=_now(),
    )
    db.add(job)
    db.flush()  # need job.id before child rows reference it

    # M8.13: commit + publish immediately, before a single provider has
    # run - a live viewer polling this job sees it exist and be RUNNING
    # right away (see app.discovery.pipeline's identical precedent).
    _publish_job_progress(db, job, request.company_profile_id)
    db.commit()
    db.refresh(job)

    sources_used: list[str] = []
    error_messages: list[str] = []
    job_log: list[dict] = []
    raw_documents: list[RawDocument] = []

    for provider_key in provider_keys:
        started_at = _now()
        try:
            provider = get_provider(provider_key)
        except KeyError as exc:
            error_messages.append(str(exc))
            failed_at = _now()
            db.add(ResearchJobProviderRun(
                research_job_id=job.id, provider_key=provider_key, started_at=started_at,
                finished_at=failed_at, status="failed", error_message=str(exc),
            ))
            job_log.append({
                "provider_key": provider_key, "started_at": started_at.isoformat(),
                "finished_at": failed_at.isoformat(), "status": "failed", "error": str(exc),
            })
            # M8.13: commit this provider's outcome + nudge immediately -
            # mirrors app.discovery.pipeline's identical per-provider commit.
            _publish_job_progress(db, job, request.company_profile_id)
            db.commit()
            continue

        try:
            outcome = provider.fetch(source_spec, context)
        except ProviderError as exc:
            error_messages.append(f"{provider_key}: {exc}")
            failed_at = _now()
            db.add(ResearchJobProviderRun(
                research_job_id=job.id, provider_key=provider_key, started_at=started_at,
                finished_at=failed_at, status="failed", error_message=str(exc),
            ))
            job_log.append({
                "provider_key": provider_key, "started_at": started_at.isoformat(),
                "finished_at": failed_at.isoformat(), "status": "failed", "error": str(exc),
            })
            _publish_job_progress(db, job, request.company_profile_id)
            db.commit()
            continue

        finished_at = _now()
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        db.add(ResearchJobProviderRun(
            research_job_id=job.id, provider_key=provider_key, started_at=started_at, finished_at=finished_at,
            duration_ms=duration_ms, request_count=outcome.request_count, api_cost=outcome.api_cost,
            token_usage=outcome.token_usage, status="completed",
        ))
        sources_used.append(provider_key)
        job_log.append({
            "provider_key": provider_key, "started_at": started_at.isoformat(), "finished_at": finished_at.isoformat(),
            "status": "completed", "document_count": len(outcome.documents), "duration_ms": duration_ms,
        })

        source = ResearchSource(
            research_job_id=job.id,
            provider_key=provider_key,
            fetched_at=finished_at,
            status="success",
        )
        db.add(source)
        db.flush()  # need source.id for RawDocument FK

        for fetched in outcome.documents:
            doc = RawDocument(
                research_source_id=source.id,
                prospect_id=request.prospect_id,
                document_type=fetched.document_type,
                raw_html=fetched.raw_html,
                raw_json=fetched.raw_json,
                extracted_text=fetched.extracted_text,
                doc_metadata=fetched.doc_metadata,
                fetched_at=finished_at,
            )
            db.add(doc)
            raw_documents.append(doc)

        # M8.13: this provider (and every RawDocument it produced) is now
        # fully written - commit + nudge before moving to the next
        # provider, mirroring app.discovery.pipeline's identical
        # per-provider commit.
        job.raw_document_count = len(raw_documents)
        job.sources_used = sources_used
        _publish_job_progress(db, job, request.company_profile_id)
        db.commit()
        db.refresh(job)

    db.flush()  # need every RawDocument.id before AI analysis references them

    # --- AI Analysis pass: engine selected by settings.RESEARCH_ANALYSIS_ENGINE_BACKEND
    # (M2 Phase 3) - "deterministic" (keyword/regex, no provider calls) by
    # default, "llm" opt-in (app.research.analysis.llm_engine.LLMAnalysisEngine,
    # the first production caller of the AI Gateway/Agent stack). See
    # app/research/analysis/registry.py's own docstring - this call site
    # is unchanged in shape from the single-engine version it replaces.
    engine = get_analysis_engine()
    analysis_outcomes: list[AnalysisOutcome] = engine.analyze(
        context,
        raw_documents,
        premium_approved=premium_approved,
        # M11 (AI Provider Hierarchy) - threaded through purely for AI
        # Gateway request logging (see GatewayRequest.company_profile_id/
        # user_id's own docstring) - both already in hand at this point in
        # the pipeline, never persisted anywhere new.
        company_profile_id=str(request.company_profile_id),
        user_id=str(triggered_by_user.id),
    )

    analyses_by_type: dict = {}
    for outcome in analysis_outcomes:
        analysis = AIAnalysis(
            research_job_id=job.id,
            prospect_id=request.prospect_id,
            analysis_type=outcome.analysis_type,
            model_used=outcome.model_used,
            prompt_version=outcome.prompt_version,
            raw_model_output=outcome.raw_model_output,
            structured_output=outcome.structured_output,
            confidence=outcome.confidence,
            reasoning=outcome.reasoning,
        )
        analysis.source_documents = [raw_documents[i] for i in outcome.source_document_indices if 0 <= i < len(raw_documents)]
        db.add(analysis)
        db.flush()  # need analysis.id for evidence rows
        analyses_by_type[outcome.analysis_type] = (analysis, outcome)

    # --- IntelligenceSnapshot: new version, unset the previous current one -
    _unset_previous_current_snapshot(db, request.prospect_id)
    next_version = _next_snapshot_version(db, request.prospect_id)

    company_analysis, company_outcome = analyses_by_type.get(AIAnalysisType.COMPANY_PROFILE, (None, None))
    buyer_analysis, buyer_outcome = analyses_by_type.get(AIAnalysisType.BUYER_PROFILE, (None, None))
    signals_analysis, signals_outcome = analyses_by_type.get(AIAnalysisType.BUSINESS_SIGNALS, (None, None))

    company_out = company_outcome.structured_output if company_outcome else {}
    buyer_out = buyer_outcome.structured_output if buyer_outcome else {}
    signals_out = signals_outcome.structured_output if signals_outcome else {}

    snapshot = IntelligenceSnapshot(
        prospect_id=request.prospect_id,
        version=next_version,
        research_job_id=job.id,
        company_profile_id=request.company_profile_id,
        is_current=True,
        business_model=company_out.get("business_model"),
        products_offered=company_out.get("products_offered") or [],
        markets_served=company_out.get("markets_served") or [],
        certifications=company_out.get("certifications") or [],
        manufacturing_or_trading=company_out.get("manufacturing_or_trading"),
        sustainability_notes=company_out.get("sustainability_notes"),
        import_export_activity=company_out.get("import_export_activity") or [],
        buyer_notes=buyer_out.get("buyer_notes"),
        procurement_structure=buyer_out.get("procurement_structure"),
        purchasing_process=buyer_out.get("purchasing_process"),
        signals_summary=signals_out.get("signals_summary"),
    )
    db.add(snapshot)
    db.flush()  # need snapshot.id for Signal/Recommendation FKs

    # --- Signals, evidenced against the RawDocuments that triggered them --
    signal_count = 0
    if signals_analysis is not None:
        for signal_draft in signals_out.get("signals", []):
            signal = Signal(
                prospect_id=request.prospect_id,
                intelligence_snapshot_id=snapshot.id,
                signal_type=signal_draft["signal_type"],
                title=signal_draft["title"],
                description=signal_draft.get("description"),
                detected_at=_now(),
                confidence=signal_draft.get("confidence"),
                reasoning=signal_draft.get("reasoning"),
                importance=SignalImportance(signal_draft.get("importance", "medium")),
                urgency=SignalUrgency(signal_draft.get("urgency", "medium")),
                status=SignalStatus.NEW,
            )
            db.add(signal)
            db.flush()
            for idx in signal_draft.get("evidence_document_indices", []):
                if 0 <= idx < len(raw_documents):
                    db.add(SignalEvidence(
                        signal_id=signal.id,
                        raw_document_id=raw_documents[idx].id,
                        ai_analysis_id=signals_analysis.id,
                    ))
            signal_count += 1

    # --- Recommendations, evidenced the same way ----------------------------
    sales_analysis, sales_outcome = analyses_by_type.get(AIAnalysisType.SALES_INTELLIGENCE, (None, None))
    recommendation_count = 0
    if sales_analysis is not None:
        sales_out = sales_outcome.structured_output
        for rec_draft in sales_out.get("recommendations", []):
            product_id = rec_draft.get("product_id")
            recommendation = Recommendation(
                prospect_id=request.prospect_id,
                intelligence_snapshot_id=snapshot.id,
                recommendation_type=RecommendationType(rec_draft.get("recommendation_type", "product_fit")),
                product_id=product_id,
                title=rec_draft["title"],
                rationale=rec_draft.get("rationale"),
                confidence=rec_draft.get("confidence"),
                reasoning=rec_draft.get("reasoning"),
                status=RecommendationStatus.NEW,
            )
            db.add(recommendation)
            db.flush()
            for idx in rec_draft.get("evidence_document_indices", []):
                if 0 <= idx < len(raw_documents):
                    db.add(RecommendationEvidence(
                        recommendation_id=recommendation.id,
                        raw_document_id=raw_documents[idx].id,
                        ai_analysis_id=sales_analysis.id,
                    ))
            recommendation_count += 1

    # --- Finally populate the seam M1 left null for a "future AI pass" -----
    prospect.ai_reasoning = (
        f"Intelligence Snapshot v{next_version}: "
        f"{signals_out.get('signals_summary') or 'no notable signals detected'}. "
        f"{recommendation_count} recommendation(s) generated."
    )

    job.sources_used = sources_used
    job.raw_document_count = len(raw_documents)
    job.signal_count = signal_count
    job.recommendation_count = recommendation_count
    job.finished_at = _now()
    job.error_message = "; ".join(error_messages) if error_messages else None
    job.log = job_log

    if not sources_used and error_messages:
        job.status = ResearchJobStatus.FAILED
    elif error_messages:
        job.status = ResearchJobStatus.PARTIALLY_COMPLETED
    else:
        job.status = ResearchJobStatus.COMPLETED

    request.status = job.status

    run = ResearchRun(
        research_request_id=request.id,
        research_job_id=job.id,
        prospect_id=request.prospect_id,
        company_profile_id=request.company_profile_id,
        triggered_by_user_id=triggered_by_user.id,
        triggered_at=job.started_at,
        config_snapshot={
            "research_template_id": str(request.research_template_id),
            "research_template_name": request.research_template.name,
            "source_spec": source_spec,
            "provider_keys": provider_keys,
        },
        documents_found_count=len(raw_documents),
        intelligence_version_created=next_version,
    )
    db.add(run)

    # M8.13: the final transition - job.status is now terminal - one last
    # nudge so a live viewer knows to fetch the completion summary.
    _publish_job_progress(db, job, request.company_profile_id)
    db.commit()
    db.refresh(job)
    return job
