"""
Synchronous Discovery pipeline orchestrator. M1 is manual-execution-only -
no Celery/Redis/BackgroundTasks/polling worker - so running a search means
doing all of this within one request/response cycle. Real trade-off: a
slow provider makes for a slow HTTP request; accepted for this milestone,
revisit if/when manual-only execution stops being sufficient.
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

    for prospect in touched_prospects.values():
        _score_and_apply(db, prospect, icp, context.products)

    job.providers_used = providers_used
    job.raw_result_count = raw_result_count
    job.prospect_created_count = created_count
    job.prospect_matched_count = matched_count
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

    db.commit()
    db.refresh(job)
    return job
