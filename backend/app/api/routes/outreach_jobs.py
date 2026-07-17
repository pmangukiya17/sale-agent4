import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.outreach_job import OutreachJob
from app.schemas.outreach_job import OutreachJobRead

router = APIRouter()

# Read-only. No provider_runs/sources/analyses child data to nest -
# Outreach fetches nothing external, only one internal channel-provider
# render call. The resulting draft lives on OutreachDraft, fetched
# separately.


@router.get("/company-profiles/{company_profile_id}/outreach-jobs", response_model=list[OutreachJobRead])
def list_outreach_jobs(
    prospect_id: uuid.UUID | None = Query(None),
    prospect_contact_id: uuid.UUID | None = Query(None),
    outreach_request_id: uuid.UUID | None = Query(None),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[OutreachJob]:
    stmt = select(OutreachJob).where(OutreachJob.company_profile_id == profile.id).order_by(OutreachJob.created_at.desc())
    if prospect_id is not None:
        stmt = stmt.where(OutreachJob.prospect_id == prospect_id)
    if prospect_contact_id is not None:
        stmt = stmt.where(OutreachJob.prospect_contact_id == prospect_contact_id)
    if outreach_request_id is not None:
        stmt = stmt.where(OutreachJob.outreach_request_id == outreach_request_id)
    return list(db.scalars(stmt).all())


@router.get("/company-profiles/{company_profile_id}/outreach-jobs/{job_id}", response_model=OutreachJobRead)
def get_outreach_job(
    job_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> OutreachJob:
    job = db.get(OutreachJob, job_id)
    if job is None or job.company_profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outreach job not found")
    return job
