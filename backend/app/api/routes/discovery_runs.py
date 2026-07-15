import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.discovery_run import DiscoveryRun
from app.schemas.discovery_run import DiscoveryRunRead

router = APIRouter()

# Read-only - a DiscoveryRun is written exactly once, by the pipeline,
# when a search executes. Nothing ever edits one after the fact; that's
# the point of it being a frozen historical snapshot.


@router.get("/company-profiles/{company_profile_id}/discovery-runs", response_model=list[DiscoveryRunRead])
def list_discovery_runs(
    discovery_search_id: uuid.UUID | None = Query(None),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[DiscoveryRun]:
    stmt = (
        select(DiscoveryRun)
        .where(DiscoveryRun.company_profile_id == profile.id)
        .order_by(DiscoveryRun.triggered_at.desc())
    )
    if discovery_search_id is not None:
        stmt = stmt.where(DiscoveryRun.discovery_search_id == discovery_search_id)
    return list(db.scalars(stmt).all())
