import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.personalization_request import PersonalizationRequest
from app.models.personalization_template import PersonalizationTemplate
from app.models.prospect import Prospect
from app.models.user import User
from app.personalization.pipeline import PERSONALIZATION_REQUEST_RUN_REQUESTED_EVENT_TYPE
from app.schemas.personalization_request import (
    PersonalizationRequestCreate,
    PersonalizationRequestRead,
    PersonalizationRequestRunBody,
    PersonalizationRequestRunQueued,
)
from app.workflow_engine.events import publish_event

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
    response_model=PersonalizationRequestRunQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_personalization_request_endpoint(
    prospect_id: uuid.UUID,
    request_id: uuid.UUID,
    run_in: PersonalizationRequestRunBody | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalizationRequestRunQueued:
    """
    M8.14: no longer runs synchronously in-request - mirrors Discovery's
    (M8.8) and Research's (M8.13) identical change. This endpoint only
    validates the request and publishes
    PERSONALIZATION_REQUEST_RUN_REQUESTED_EVENT_TYPE (subject_type=
    "personalization_request", subject_id=request.id, actor_type="user",
    actor_id=str(current_user.id)). Unlike Research, there is no run_input
    to carry in the event's payload - Personalization only reads what's
    already stored (current Intelligence Snapshot, Signals,
    Recommendations, ICP, Products, Knowledge Base) - `run_in` remains the
    same unused placeholder it already was on the synchronous path (see
    PersonalizationRequestRunBody's own docstring).

    The real execution happens asynchronously via the
    "personalization_request_execution" WorkflowDefinition. The frontend
    finds the resulting job by polling
    GET .../personalization-jobs?personalization_request_id={request_id}.
    """
    request = _get_request_or_404(db, profile.id, prospect_id, request_id)

    publish_event(
        db,
        event_type=PERSONALIZATION_REQUEST_RUN_REQUESTED_EVENT_TYPE,
        company_profile_id=profile.id,
        source="app.api.routes.personalization_requests",
        subject_type="personalization_request",
        subject_id=request.id,
        actor_type="user",
        actor_id=str(current_user.id),
    )
    db.commit()

    return PersonalizationRequestRunQueued(status="queued", personalization_request_id=request.id)
