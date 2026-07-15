import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.research_run import ResearchRun
from app.schemas.research_run import ResearchRunRead

router = APIRouter()

# Read-only - a ResearchRun is written exactly once, by the pipeline, when
# a research request executes. Nothing ever edits one after the fact;
# that's the point of it being a frozen historical snapshot (mirrors
# DiscoveryRun / discovery_runs.py exactly).


@router.get("/company-profiles/{company_profile_id}/research-runs", response_model=list[ResearchRunRead])
def list_research_runs(
    prospect_id: uuid.UUID | None = Query(None),
    research_request_id: uuid.UUID | None = Query(None),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[ResearchRun]:
    stmt = (
        select(ResearchRun)
        .where(ResearchRun.company_profile_id == profile.id)
        .order_by(ResearchRun.triggered_at.desc())
    )
    if prospect_id is not None:
        stmt = stmt.where(ResearchRun.prospect_id == prospect_id)
    if research_request_id is not None:
        stmt = stmt.where(ResearchRun.research_request_id == research_request_id)
    return list(db.scalars(stmt).all())
