import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.research_job import ResearchJob
from app.models.research_source import ResearchSource
from app.schemas.research_job import ResearchJobRead

router = APIRouter()


def _job_options():
    return (
        selectinload(ResearchJob.provider_runs),
        selectinload(ResearchJob.sources).selectinload(ResearchSource.raw_documents),
        selectinload(ResearchJob.analyses),
    )


@router.get("/company-profiles/{company_profile_id}/research-jobs", response_model=list[ResearchJobRead])
def list_research_jobs(
    prospect_id: uuid.UUID | None = Query(None),
    research_request_id: uuid.UUID | None = Query(None),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[ResearchJob]:
    stmt = (
        select(ResearchJob)
        .where(ResearchJob.company_profile_id == profile.id)
        .options(*_job_options())
        .order_by(ResearchJob.created_at.desc())
    )
    if prospect_id is not None:
        stmt = stmt.where(ResearchJob.prospect_id == prospect_id)
    if research_request_id is not None:
        stmt = stmt.where(ResearchJob.research_request_id == research_request_id)
    return list(db.scalars(stmt).all())


@router.get("/company-profiles/{company_profile_id}/research-jobs/{job_id}", response_model=ResearchJobRead)
def get_research_job(
    job_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ResearchJob:
    stmt = select(ResearchJob).where(ResearchJob.id == job_id).options(*_job_options())
    job = db.scalars(stmt).first()
    if job is None or job.company_profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research job not found")
    return job
