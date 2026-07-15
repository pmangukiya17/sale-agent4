import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.prospect import Prospect
from app.models.research_job import ResearchJob
from app.models.research_request import ResearchRequest
from app.models.research_template import ResearchTemplate
from app.models.user import User
from app.research.pipeline import ResearchConfigError, run_research_request
from app.schemas.research_job import ResearchJobRead
from app.schemas.research_request import ResearchRequestCreate, ResearchRequestRead, ResearchRequestRunBody

router = APIRouter()


def _get_prospect_or_404(db: Session, profile_id: uuid.UUID, prospect_id: uuid.UUID) -> Prospect:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None or prospect.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return prospect


def _validate_template(db: Session, profile_id: uuid.UUID, template_id: uuid.UUID) -> None:
    template = db.get(ResearchTemplate, template_id)
    if template is None or (template.company_profile_id != profile_id and not template.is_system_default):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown research_template_id")


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/research-requests",
    response_model=list[ResearchRequestRead],
)
def list_research_requests(
    prospect_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[ResearchRequest]:
    _get_prospect_or_404(db, profile.id, prospect_id)
    stmt = (
        select(ResearchRequest)
        .where(ResearchRequest.prospect_id == prospect_id)
        .order_by(ResearchRequest.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/research-requests",
    response_model=ResearchRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_research_request(
    prospect_id: uuid.UUID,
    request_in: ResearchRequestCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResearchRequest:
    _get_prospect_or_404(db, profile.id, prospect_id)
    _validate_template(db, profile.id, request_in.research_template_id)
    request = ResearchRequest(
        prospect_id=prospect_id,
        company_profile_id=profile.id,
        requested_by_user_id=current_user.id,
        **request_in.model_dump(),
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def _get_request_or_404(db: Session, profile_id: uuid.UUID, prospect_id: uuid.UUID, request_id: uuid.UUID) -> ResearchRequest:
    request = db.get(ResearchRequest, request_id)
    if request is None or request.company_profile_id != profile_id or request.prospect_id != prospect_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research request not found")
    return request


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/research-requests/{request_id}",
    response_model=ResearchRequestRead,
)
def get_research_request(
    prospect_id: uuid.UUID,
    request_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ResearchRequest:
    return _get_request_or_404(db, profile.id, prospect_id, request_id)


@router.post(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/research-requests/{request_id}/run",
    response_model=ResearchJobRead,
    status_code=status.HTTP_201_CREATED,
)
def run_research_request_endpoint(
    prospect_id: uuid.UUID,
    request_id: uuid.UUID,
    run_in: ResearchRequestRunBody | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResearchJob:
    """
    Runs synchronously, in-request - no Celery/Redis/BackgroundTasks/
    polling worker in M2. run_in supplies the per-run input (e.g. the
    manual_document provider's "documents") since ResearchRequest itself
    has no persisted source_spec column - see pipeline.py's docstring.
    """
    request = _get_request_or_404(db, profile.id, prospect_id, request_id)
    run_input = run_in.model_dump(exclude_none=True) if run_in is not None else None
    try:
        return run_research_request(db, request, current_user, run_input=run_input)
    except ResearchConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
