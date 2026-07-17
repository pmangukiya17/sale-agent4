import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.personalization_run import PersonalizationRun
from app.schemas.personalization_run import PersonalizationRunRead

router = APIRouter()

# Read-only - a PersonalizationRun is written exactly once, by the
# pipeline, when a request executes. Nothing ever edits one after the
# fact; that's the point of it being a frozen historical snapshot.


@router.get("/company-profiles/{company_profile_id}/personalization-runs", response_model=list[PersonalizationRunRead])
def list_personalization_runs(
    prospect_id: uuid.UUID | None = Query(None),
    personalization_request_id: uuid.UUID | None = Query(None),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[PersonalizationRun]:
    stmt = (
        select(PersonalizationRun)
        .where(PersonalizationRun.company_profile_id == profile.id)
        .order_by(PersonalizationRun.triggered_at.desc())
    )
    if prospect_id is not None:
        stmt = stmt.where(PersonalizationRun.prospect_id == prospect_id)
    if personalization_request_id is not None:
        stmt = stmt.where(PersonalizationRun.personalization_request_id == personalization_request_id)
    return list(db.scalars(stmt).all())
