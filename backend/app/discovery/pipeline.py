"""
Discovery pipeline orchestrator.

M8.8 update: this function is now ALSO reachable asynchronously, via
DiscoveryExecutionAction (app/workflow_actions/discovery_execution_action.py),
triggered off a real Event through the M7 Workflow Engine rather than only
from the synchronous /run route. To make that path produce genuinely LIVE,
incremental progress (not one atomic all-or-nothing write at the very end),
this function now commits at three points instead of one: right after the
DiscoveryJob row is created (so a poller sees "running" immediately, before
any provider has even started), once per provider as it finishes (success
or failure), and once at final completion - each commit paired with a real
publish_event(DISCOVERY_JOB_PROGRESS_EVENT_TYPE) so a live UI is told to
re-fetch, the same "arrival is a nudge to re-fetch, never itself the
payload of truth" pattern M8.5/M8.6 already established for Notifications/
the real-time stream. The synchronous /run route no longer calls this
directly (see app/api/routes/discovery_searches.py) - it publishes
DISCOVERY_SEARCH_RUN_REQUESTED_EVENT_TYPE instead - but this function's own
signature and every one of its existing synchronous callers (tests,
scripts) continue to work completely unchanged; incremental commits are an
internal implementation detail, not a contract change.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.discovery.context import DiscoveryContext
from app.discovery.dedup import find_duplicate
from app.discovery.providers.base import ProviderError
from app.discovery.providers.registry import get_provider
from app.discovery.scoring import score_prospect
from app.models.company_profile import CompanyProfile
from app.models.discovery_job import DiscoveryJob
from app.models.discovery_job_provider_run import DiscoveryJobProviderRun
from app.models.discovery_provider_result import DiscoveryProviderResult
from app.models.discovery_run import DiscoveryRun
from app.models.discovery_search import DiscoverySearch
from app.models.enums import DiscoveryJobStatus, ProductStatus, ProspectStatus
from app.models.icp_criteria import ICPCriteria
from app.models.knowledge_base import KnowledgeBase
from app.models.product import Product
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.prospect_source import ProspectSource
from app.models.prospect_timeline_event import ProspectTimelineEvent
from app.models.user import User
from app.workflow_engine.events import publish_event

# M8.8: the two Discovery event types the Live Workflow Visualization is
# built on. RUN_REQUESTED is published once, by the /run route, as the
# trigger for the "discovery_search_execution" built-in WorkflowDefinition
# (app/workflow_bootstrap.py). PROGRESS is published from inside this
# module, every time discovery_jobs (or its provider-run children) changes
# in a way a live viewer should re-fetch for - it deliberately carries no
# business data of its own (just enough to identify the job), exactly like
# every other Event in this codebase: an arrival signal, not the payload of
# truth. The real, authoritative state is always re-read from
# GET /company-profiles/{id}/discovery-jobs/{job_id}.
DISCOVERY_SEARCH_RUN_REQUESTED_EVENT_TYPE = "discovery_search.run_requested"
DISCOVERY_JOB_PROGRESS_EVENT_TYPE = "discovery_job.progress"

# Prospects a human has already made a call on are never re-scored or
# re-statused by a later run - a re-surfacing just bumps last_seen_at and
# records a new source, it doesn't relitigate a human decision.
_REVIEWED_TERMINAL_STATUSES = {ProspectStatus.APPROVED, ProspectStatus.REJECTED, ProspectStatus.ARCHIVED}


class DiscoveryConfigError(Exception):
    """Raised when a search can't run because of missing configuration
    (no active ICP, unknown provider, ...) - a 400, not a 500."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_icp(db: Session, search: DiscoverySearch) -> ICPCriteria:
    if search.icp_criteria_id is not None:
        icp = db.get(ICPCriteria, search.icp_criteria_id)
        if icp is None:
            raise DiscoveryConfigError("This search's pinned ICP criteria no longer exists.")
        return icp

    stmt = select(ICPCriteria).where(
        ICPCriteria.company_profile_id == search.company_profile_id,
        ICPCriteria.is_active.is_(True),
    )
    icp = db.scalars(stmt).first()
    if icp is None:
        raise DiscoveryConfigError(
            "No active ICP criteria configured for this business. Create/activate one before running a search."
        )
    return icp


def _build_context(db: Session, company_profile: CompanyProfile, icp: ICPCriteria) -> DiscoveryContext:
    products = list(
        db.scalars(
            select(Product).where(
                Product.company_profile_id == company_profile.id,
                Product.status == ProductStatus.ACTIVE,
            )
        ).all()
    )
    kb_entries = list(
        db.scalars(select(KnowledgeBase).where(KnowledgeBase.company_profile_id == company_profile.id)).all()
    )
    return DiscoveryContext(company_profile=company_profile, icp=icp, products=products, knowledge_base_entries=kb_entries)


def _merged_query_spec(search: DiscoverySearch) -> dict:
    template_spec = search.search_template.query_spec or {}
    return {**template_spec, **(search.query_spec or {})}


def _score_and_apply(db: Session, prospect: Prospect, icp: ICPCriteria, products: list[Product]) -> None:
    if ProspectStatus(prospect.status) in _REVIEWED_TERMINAL_STATUSES:
        return

    result = score_prospect(prospect, icp, products)
    prospect.total_score = result.total_score
    prospect.score_breakdown = result.breakdown

    if result.excluded:
        prospect.status = ProspectStatus.UNQUALIFIED
    elif prospect.status == ProspectStatus.DUPLICATE_REVIEW:
        pass  # stays flagged for a human to resolve, regardless of score
    else:
        threshold = icp.minimum_confidence_score
        qualifies = threshold is None or (result.total_score / 100.0) >= threshold
        prospect.status = ProspectStatus.QUALIFIED if qualifies else ProspectStatus.UNQUALIFIED

    db.add(ProspectTimelineEvent(prospect_id=prospect.id, event_type="score_updated", actor="system", payload={
        "total_score": prospect.total_score, "status": prospect.status.value if hasattr(prospect.status, "value") else prospect.status,
    }))


def _publish_job_progress(db: Session, job: DiscoveryJob, company_profile_id) -> None:
    """One nudge, no payload beyond enough to identify the job - see this
    module's own docstring for why. Flushes but does not commit; callers
    always pair this with their own db.commit() immediately after, so the
    Event and whatever domain write it's reporting land in the same
    transaction (transactional outbox, per publish_event's own contract)."""
    publish_event(
        db,
        event_type=DISCOVERY_JOB_PROGRESS_EVENT_TYPE,
        company_profile_id=company_profile_id,
        source="app.discovery.pipeline",
        subject_type="discovery_job",
        subject_id=job.id,
        payload={"status": job.status.value if hasattr(job.status, "value") else job.status},
    )


def run_discovery_search(db: Session, search: DiscoverySearch, triggered_by_user: User) -> DiscoveryJob:
    icp = _resolve_icp(db, search)
    company_profile = db.get(CompanyProfile, search.company_profile_id)
    context = _build_context(db, company_profile, icp)
    query_spec = _merged_query_spec(search)

    job = DiscoveryJob(
        discovery_search_id=search.id,
        company_profile_id=search.company_profile_id,
        status=DiscoveryJobStatus.RUNNING,
        started_at=_now(),
    )
    db.add(job)
    db.flush()  # need job.id before child rows reference it

    # M8.8: commit + publish immediately, before a single provider has run -
    # a live viewer polling GET .../discovery-jobs/{job.id} sees this job
    # exist and be RUNNING right away, instead of only once everything is
    # already finished.
    _publish_job_progress(db, job, search.company_profile_id)
    db.commit()
    db.refresh(job)

    existing_prospects = list(
        db.scalars(select(Prospect).where(Prospect.company_profile_id == search.company_profile_id)).all()
    )
    touched_prospects: dict = {}  # id -> Prospect, for the scoring pass at the end

    providers_used: list[str] = []
    any_failure = False
    raw_result_count = 0
    created_count = 0
    matched_count = 0
    duplicate_flag_count = 0
    error_messages: list[str] = []
    job_log: list[dict] = []

    for provider_key in search.provider_keys:
        started_at = _now()
        try:
            provider = get_provider(provider_key)
        except KeyError as exc:
            any_failure = True
            error_messages.append(str(exc))
            failed_at = _now()
            db.add(DiscoveryJobProviderRun(
                discovery_job_id=job.id, provider_key=provider_key, started_at=started_at,
                finished_at=failed_at, status="failed", error_message=str(exc),
            ))
            job_log.append({
                "provider_key": provider_key, "started_at": started_at.isoformat(),
                "finished_at": failed_at.isoformat(), "status": "failed", "error": str(exc),
            })
            # M8.8: commit this provider's outcome + nudge immediately -
            # a live viewer sees THIS provider fail the moment it fails,
            # not only once every other provider has also finished.
            _publish_job_progress(db, job, search.company_profile_id)
            db.commit()
            continue

        try:
            outcome = provider.search(query_spec, context)
        except ProviderError as exc:
            any_failure = True
            error_messages.append(f"{provider_key}: {exc}")
            failed_at = _now()
            db.add(DiscoveryJobProviderRun(
                discovery_job_id=job.id, provider_key=provider_key, started_at=started_at,
                finished_at=failed_at, status="failed", error_message=str(exc),
            ))
            job_log.append({
                "provider_key": provider_key, "started_at": started_at.isoformat(),
                "finished_at": failed_at.isoformat(), "status": "failed", "error": str(exc),
            })
            _publish_job_progress(db, job, search.company_profile_id)
            db.commit()
            continue

        finished_at = _now()
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        db.add(DiscoveryJobProviderRun(
            discovery_job_id=job.id, provider_key=provider_key, started_at=started_at, finished_at=finished_at,
            duration_ms=duration_ms, request_count=outcome.request_count, api_cost=outcome.api_cost,
            token_usage=outcome.token_usage, status="completed",
        ))
        providers_used.append(provider_key)
        raw_result_count += len(outcome.results)
        job_log.append({
            "provider_key": provider_key, "started_at": started_at.isoformat(), "finished_at": finished_at.isoformat(),
            "status": "completed", "result_count": len(outcome.results), "duration_ms": duration_ms,
        })

        for raw in outcome.results:
            fetched_at = _now()
            provider_result = DiscoveryProviderResult(
                discovery_job_id=job.id,
                provider_key=provider_key,
                raw_payload=raw.raw_payload,
                fetched_at=fetched_at,
                normalized_payload={
                    "name": raw.name, "website": raw.website, "country": raw.country,
                    "industry_raw": raw.industry_raw, "company_size_range": raw.company_size_range,
                    "description": raw.description,
                },
                dedup_key=raw.website or raw.name,
            )
            db.add(provider_result)
            db.flush()  # need provider_result.id for the ProspectSource FK

            match = find_duplicate(existing_prospects, name=raw.name, website=raw.website, country=raw.country)

            if match and match.is_definite:
                prospect = match.prospect
                prospect.last_seen_at = fetched_at
                matched_count += 1
                db.add(ProspectTimelineEvent(
                    prospect_id=prospect.id, event_type="reseen_by_provider", actor="system",
                    payload={"provider_key": provider_key, "discovery_job_id": str(job.id)},
                ))
            else:
                prospect = Prospect(
                    company_profile_id=search.company_profile_id,
                    discovery_search_id=search.id,
                    name=raw.name,
                    website=raw.website,
                    country=raw.country,
                    industry_raw=raw.industry_raw,
                    company_size_range=raw.company_size_range,
                    description=raw.description,
                    status=ProspectStatus.NEW,
                    first_discovered_at=fetched_at,
                    last_seen_at=fetched_at,
                    timezone=None,
                )
                if match:  # potential (non-definite) match - flag, don't merge
                    prospect.status = ProspectStatus.DUPLICATE_REVIEW
                    prospect.potential_duplicate_of_prospect_id = match.prospect.id
                    prospect.duplicate_confidence = match.confidence
                    duplicate_flag_count += 1
                db.add(prospect)
                db.flush()
                existing_prospects.append(prospect)
                created_count += 1
                db.add(ProspectTimelineEvent(
                    prospect_id=prospect.id, event_type="discovered", actor="system",
                    payload={"provider_key": provider_key, "discovery_job_id": str(job.id)},
                ))
                if match:
                    db.add(ProspectTimelineEvent(
                        prospect_id=prospect.id, event_type="flagged_potential_duplicate", actor="system",
                        payload={"potential_duplicate_of_prospect_id": str(match.prospect.id), "confidence": match.confidence},
                    ))

            db.add(ProspectSource(
                prospect_id=prospect.id,
                provider_key=provider_key,
                source_url=raw.source_url,
                discovered_at=fetched_at,
                provider_confidence=raw.provider_confidence,
                raw_result_id=provider_result.id,
            ))
            for contact in raw.contacts:
                db.add(ProspectContact(
                    prospect_id=prospect.id,
                    name=contact.name,
                    role=contact.role,
                    department=contact.department,
                    decision_maker_level=contact.decision_maker_level or "unknown",
                    email=contact.email,
                    phone=contact.phone,
                    source=provider_key,
                    confidence=contact.confidence,
                ))

            touched_prospects[prospect.id] = prospect

        # M8.8: this provider (and every prospect/result it produced) is
        # now fully written - commit + nudge before moving to the next
        # provider, so a live viewer's provider list fills in one entry at
        # a time as each real provider actually finishes, never all at once
        # at the very end.
        job.raw_result_count = raw_result_count
        job.providers_used = providers_used
        _publish_job_progress(db, job, search.company_profile_id)
        db.commit()
        db.refresh(job)

    for prospect in touched_prospects.values():
        _score_and_apply(db, prospect, icp, context.products)

    qualified_count = sum(1 for p in touched_prospects.values() if p.status == ProspectStatus.QUALIFIED)
    rejected_count = sum(1 for p in touched_prospects.values() if p.status == ProspectStatus.UNQUALIFIED)

    job.providers_used = providers_used
    job.raw_result_count = raw_result_count
    job.prospect_created_count = created_count
    job.prospect_matched_count = matched_count
    job.prospect_qualified_count = qualified_count
    job.prospect_rejected_count = rejected_count
    job.finished_at = _now()
    job.error_message = "; ".join(error_messages) if error_messages else None
    job.log = job_log

    if not providers_used and error_messages:
        job.status = DiscoveryJobStatus.FAILED
    elif error_messages:
        job.status = DiscoveryJobStatus.PARTIALLY_COMPLETED
    else:
        job.status = DiscoveryJobStatus.COMPLETED

    run = DiscoveryRun(
        discovery_search_id=search.id,
        discovery_job_id=job.id,
        company_profile_id=search.company_profile_id,
        triggered_by_user_id=triggered_by_user.id,
        triggered_at=job.started_at,
        config_snapshot={
            "search_template_id": str(search.search_template_id),
            "search_template_name": search.search_template.name,
            "icp_criteria_id": str(icp.id),
            "icp_version": icp.version,
            "query_spec": query_spec,
            "provider_keys": search.provider_keys,
            "search_depth": search.search_depth.value if hasattr(search.search_depth, "value") else search.search_depth,
        },
        prospects_found_count=created_count + matched_count,
        new_prospects_count=created_count,
        duplicate_count=matched_count + duplicate_flag_count,
    )
    db.add(run)

    # M8.8: the final transition - job.status is now terminal
    # (COMPLETED/PARTIALLY_COMPLETED/FAILED) - one last nudge so a live
    # viewer knows to fetch the completion summary.
    _publish_job_progress(db, job, search.company_profile_id)
    db.commit()
    db.refresh(job)
    return job
