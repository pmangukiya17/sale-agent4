import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.outreach_run import OutreachRun
from app.schemas.outreach_run import OutreachRunRead

router = APIRouter()

# Read-only, frozen forever once created - see OutreachRun's docstring.


@router.get("/company-profiles/{company_profile_id}/outreach-runs", response_model=list[OutreachRunRead])
def list_outreach_runs(
    prospect_id: uuid.UUID | None = Query(None),
    prospect_contact_id: uuid.UUID | None = Query(None),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[OutreachRun]:
    stmt = select(OutreachRun).where(OutreachRun.company_profile_id == profile.id).order_by(OutreachRun.triggered_at.desc())
    if prospect_id is not None:
        stmt = stmt.where(OutreachRun.prospect_id == prospect_id)
    if prospect_contact_id is not None:
        stmt = stmt.where(OutreachRun.prospect_contact_id == prospect_contact_id)
    return list(db.scalars(stmt).all())


@router.get("/company-profiles/{company_profile_id}/outreach-runs/{run_id}", response_model=OutreachRunRead)
def get_outreach_run(
    run_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> OutreachRun:
    run = db.get(OutreachRun, run_id)
    if run is None or run.company_profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outreach run not found")
    return run
