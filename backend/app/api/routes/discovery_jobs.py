import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.discovery_job import DiscoveryJob
from app.schemas.discovery_job import DiscoveryJobRead

router = APIRouter()


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
    job = db.get(DiscoveryJob, job_id)
    if job is None or job.company_profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discovery job not found")
    return job
