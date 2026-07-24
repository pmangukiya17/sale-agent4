import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.discovery.pipeline import DISCOVERY_JOB_PROGRESS_EVENT_TYPE
from app.models.company_profile import CompanyProfile
from app.models.discovery_job import DiscoveryJob
from app.models.enums import DiscoveryJobStatus
from app.models.user import User
from app.schemas.discovery_job import DiscoveryJobCancelRequest, DiscoveryJobRead
from app.workflow_engine.events import publish_event

router = APIRouter()

# M2 Phase 1c: cancellation is only meaningful from RUNNING - every other
# status is already terminal (or, for PENDING, not actually reachable
# externally today - see DiscoveryJob's own model docstring: jobs are
# created directly as RUNNING, never PENDING). Kept as an explicit set
# rather than a single equality check so a future PENDING-producing
# execution path (e.g. a real queueing layer) is automatically
# cancellable too, without revisiting this route.
_CANCELLABLE_STATUSES = {DiscoveryJobStatus.PENDING, DiscoveryJobStatus.RUNNING}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_job_or_404(db: Session, profile_id: uuid.UUID, job_id: uuid.UUID) -> DiscoveryJob:
    job = db.get(DiscoveryJob, job_id)
    if job is None or job.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discovery job not found")
    return job


@router.get("/company-profiles/{company_profile_id}/discovery-jobs", response_model=list[DiscoveryJobRead])
def list_discovery_jobs(
    discovery_search_id: uuid.UUID | None = Query(None),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[DiscoveryJob]:
    stmt = (
        select(DiscoveryJob)
        .where(DiscoveryJob.company_profile_id == profile.id)
        .options(selectinload(DiscoveryJob.provider_runs))
        .order_by(DiscoveryJob.created_at.desc())
    )
    if discovery_search_id is not None:
        stmt = stmt.where(DiscoveryJob.discovery_search_id == discovery_search_id)
    return list(db.scalars(stmt).all())


@router.get("/company-profiles/{company_profile_id}/discovery-jobs/{job_id}", response_model=DiscoveryJobRead)
def get_discovery_job(
    job_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> DiscoveryJob:
    return _get_job_or_404(db, profile.id, job_id)


@router.post(
    "/company-profiles/{company_profile_id}/discovery-jobs/{job_id}/cancel",
    response_model=DiscoveryJobRead,
)
def cancel_discovery_job(
    job_id: uuid.UUID,
    cancel_in: DiscoveryJobCancelRequest | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DiscoveryJob:
    """M2 Phase 1c - Discovery Job graceful cancellation.

    Deliberately does NOT set job.status directly - only
    app.discovery.pipeline.run_discovery_search() (the one function
    actually executing this job, synchronously, possibly in a
    completely different process/worker tick) is allowed to write
    DiscoveryJobStatus.CANCELLED, at a safe checkpoint between units of
    work, once it has observed this request - see that module's own
    docstring for the full reasoning and exactly how it's observed
    (job.cancel_requested_at, re-read via db.refresh() for real
    cross-session visibility).

    Rejects (400) a job that's already terminal - COMPLETED/
    PARTIALLY_COMPLETED/FAILED/CANCELLED can't be cancelled, there's
    nothing left running to stop. Idempotent for a job that's still
    RUNNING but already had cancellation requested (e.g. a double click,
    or a retry after a slow response) - re-affirms the existing request
    rather than erroring or overwriting the original requester/timestamp.
    """
    job = _get_job_or_404(db, profile.id, job_id)

    if job.status not in _CANCELLABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Discovery job cannot be cancelled from status '{job.status.value}' - it has already finished.",
        )

    if job.cancel_requested_at is not None:
        # Already requested (by this or an earlier call) - nothing new to
        # do; return current state rather than erroring on a harmless repeat.
        return job

    job.cancel_requested_at = _now()
    job.cancel_requested_by_user_id = current_user.id
    reason = cancel_in.reason if cancel_in is not None else None
    job.log = [*job.log, {
        "event": "cancellation_requested", "requested_by_user_id": str(current_user.id),
        **({"reason": reason} if reason else {}),
    }]
    # Same nudge every other job-state change already publishes - a live
    # viewer sees "cancellation requested" immediately, before the
    # worker has had a chance to actually observe and act on it.
    publish_event(
        db,
        event_type=DISCOVERY_JOB_PROGRESS_EVENT_TYPE,
        company_profile_id=profile.id,
        source="app.api.routes.discovery_jobs",
        subject_type="discovery_job",
        subject_id=job.id,
        payload={"status": job.status.value, "cancellation_requested": True},
    )
    db.commit()
    db.refresh(job)
    return job
