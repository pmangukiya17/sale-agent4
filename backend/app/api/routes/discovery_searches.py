import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.discovery.pipeline import DiscoveryConfigError, run_discovery_search
from app.models.company_profile import CompanyProfile
from app.models.discovery_job import DiscoveryJob
from app.models.discovery_search import DiscoverySearch
from app.models.icp_criteria import ICPCriteria
from app.models.search_template import SearchTemplate
from app.models.user import User
from app.schemas.discovery_job import DiscoveryJobRead
from app.schemas.discovery_search import DiscoverySearchCreate, DiscoverySearchRead, DiscoverySearchUpdate

router = APIRouter()


def _validate_template(db: Session, profile_id: uuid.UUID, template_id: uuid.UUID) -> None:
    template = db.get(SearchTemplate, template_id)
    if template is None or (template.company_profile_id != profile_id and not template.is_system_default):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown search_template_id")


def _validate_icp(db: Session, profile_id: uuid.UUID, icp_criteria_id: uuid.UUID | None) -> None:
    if icp_criteria_id is None:
        return
    icp = db.get(ICPCriteria, icp_criteria_id)
    if icp is None or icp.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown icp_criteria_id")


@router.get("/company-profiles/{company_profile_id}/discovery-searches", response_model=list[DiscoverySearchRead])
def list_discovery_searches(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[DiscoverySearch]:
    stmt = (
        select(DiscoverySearch)
        .where(DiscoverySearch.company_profile_id == profile.id)
        .order_by(DiscoverySearch.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("/company-profiles/{company_profile_id}/discovery-searches", response_model=DiscoverySearchRead, status_code=status.HTTP_201_CREATED)
def create_discovery_search(
    search_in: DiscoverySearchCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> DiscoverySearch:
    _validate_template(db, profile.id, search_in.search_template_id)
    _validate_icp(db, profile.id, search_in.icp_criteria_id)
    search = DiscoverySearch(company_profile_id=profile.id, **search_in.model_dump())
    db.add(search)
    db.commit()
    db.refresh(search)
    return search


def _get_search_or_404(db: Session, profile_id: uuid.UUID, search_id: uuid.UUID) -> DiscoverySearch:
    search = db.get(DiscoverySearch, search_id)
    if search is None or search.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discovery search not found")
    return search


@router.get("/company-profiles/{company_profile_id}/discovery-searches/{search_id}", response_model=DiscoverySearchRead)
def get_discovery_search(
    search_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> DiscoverySearch:
    return _get_search_or_404(db, profile.id, search_id)


@router.put("/company-profiles/{company_profile_id}/discovery-searches/{search_id}", response_model=DiscoverySearchRead)
def update_discovery_search(
    search_id: uuid.UUID,
    search_in: DiscoverySearchUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> DiscoverySearch:
    search = _get_search_or_404(db, profile.id, search_id)
    data = search_in.model_dump(exclude_unset=True)
    if "search_template_id" in data and data["search_template_id"] is not None:
        _validate_template(db, profile.id, data["search_template_id"])
    if "icp_criteria_id" in data:
        _validate_icp(db, profile.id, data["icp_criteria_id"])
    for field, value in data.items():
        setattr(search, field, value)
    db.commit()
    db.refresh(search)
    return search


@router.delete("/company-profiles/{company_profile_id}/discovery-searches/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_discovery_search(
    search_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> None:
    search = _get_search_or_404(db, profile.id, search_id)
    db.delete(search)
    db.commit()


@router.post(
    "/company-profiles/{company_profile_id}/discovery-searches/{search_id}/run",
    response_model=DiscoveryJobRead,
    status_code=status.HTTP_201_CREATED,
)
def run_search(
    search_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DiscoveryJob:
    """
    Runs synchronously, in-request - no Celery/Redis/BackgroundTasks/
    polling worker in M1. The full result (job status, counts, per-provider
    metrics) comes back in this same response.
    """
    search = _get_search_or_404(db, profile.id, search_id)
    if not search.provider_keys:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This search has no providers enabled")
    try:
        return run_discovery_search(db, search, current_user)
    except DiscoveryConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
