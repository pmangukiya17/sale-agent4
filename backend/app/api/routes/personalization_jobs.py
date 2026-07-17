import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.personalization_job import PersonalizationJob
from app.schemas.personalization_job import PersonalizationJobRead

router = APIRouter()

# Read-only. Unlike DiscoveryJob/ResearchJob there is no provider_runs/
# sources/analyses child data to nest - Personalization has nothing to
# fetch, only one internal engine call. The resulting strategy lives on
# PersonalizationSnapshot, fetched separately.


@router.get("/company-profiles/{company_profile_id}/personalization-jobs", response_model=list[PersonalizationJobRead])
def list_personalization_jobs(
    prospect_id: uuid.UUID | None = Query(None),
    personalization_request_id: uuid.UUID | None = Query(None),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[PersonalizationJob]:
    stmt = (
        select(PersonalizationJob)
        .where(PersonalizationJob.company_profile_id == profile.id)
        .order_by(PersonalizationJob.created_at.desc())
    )
    if prospect_id is not None:
        stmt = stmt.where(PersonalizationJob.prospect_id == prospect_id)
    if personalization_request_id is not None:
        stmt = stmt.where(PersonalizationJob.personalization_request_id == personalization_request_id)
    return list(db.scalars(stmt).all())


@router.get("/company-profiles/{company_profile_id}/personalization-jobs/{job_id}", response_model=PersonalizationJobRead)
def get_personalization_job(
    job_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> PersonalizationJob:
    job = db.get(PersonalizationJob, job_id)
    if job is None or job.company_profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Personalization job not found")
    return job
