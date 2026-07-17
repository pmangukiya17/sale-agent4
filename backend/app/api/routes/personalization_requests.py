import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.personalization_job import PersonalizationJob
from app.models.personalization_request import PersonalizationRequest
from app.models.personalization_template import PersonalizationTemplate
from app.models.prospect import Prospect
from app.models.user import User
from app.personalization.pipeline import PersonalizationConfigError, run_personalization_request
from app.schemas.personalization_job import PersonalizationJobRead
from app.schemas.personalization_request import (
    PersonalizationRequestCreate,
    PersonalizationRequestRead,
    PersonalizationRequestRunBody,
)

router = APIRouter()


def _get_prospect_or_404(db: Session, profile_id: uuid.UUID, prospect_id: uuid.UUID) -> Prospect:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None or prospect.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return prospect


def _validate_template(db: Session, profile_id: uuid.UUID, template_id: uuid.UUID) -> None:
    template = db.get(PersonalizationTemplate, template_id)
    if template is None or (template.company_profile_id != profile_id and not template.is_system_default):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown personalization_template_id")


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/personalization-requests",
    response_model=list[PersonalizationRequestRead],
)
def list_personalization_requests(
    prospect_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[PersonalizationRequest]:
    _get_prospect_or_404(db, profile.id, prospect_id)
    stmt = (
        select(PersonalizationRequest)
        .where(PersonalizationRequest.prospect_id == prospect_id)
        .order_by(PersonalizationRequest.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/personalization-requests",
    response_model=PersonalizationRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_personalization_request(
    prospect_id: uuid.UUID,
    request_in: PersonalizationRequestCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalizationRequest:
    _get_prospect_or_404(db, profile.id, prospect_id)
    _validate_template(db, profile.id, request_in.personalization_template_id)
    request = PersonalizationRequest(
        prospect_id=prospect_id,
        company_profile_id=profile.id,
        requested_by_user_id=current_user.id,
        **request_in.model_dump(),
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def _get_request_or_404(db: Session, profile_id: uuid.UUID, prospect_id: uuid.UUID, request_id: uuid.UUID) -> PersonalizationRequest:
    request = db.get(PersonalizationRequest, request_id)
    if request is None or request.company_profile_id != profile_id or request.prospect_id != prospect_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Personalization request not found")
    return request


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/personalization-requests/{request_id}",
    response_model=PersonalizationRequestRead,
)
def get_personalization_request(
    prospect_id: uuid.UUID,
    request_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> PersonalizationRequest:
    return _get_request_or_404(db, profile.id, prospect_id, request_id)


@router.post(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/personalization-requests/{request_id}/run",
    response_model=PersonalizationJobRead,
    status_code=status.HTTP_201_CREATED,
)
def run_personalization_request_endpoint(
    prospect_id: uuid.UUID,
    request_id: uuid.UUID,
    run_in: PersonalizationRequestRunBody | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalizationJob:
    """
    Runs synchronously, in-request - no Celery/Redis/BackgroundTasks/
    polling worker in M3. Unlike Research's /run, there is no external
    input to merge in - Personalization only reads what's already stored
    (current Intelligence Snapshot, Signals, Recommendations, ICP,
    Products, Knowledge Base).
    """
    request = _get_request_or_404(db, profile.id, prospect_id, request_id)
    try:
        return run_personalization_request(db, request, current_user)
    except PersonalizationConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
