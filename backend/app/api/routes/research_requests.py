import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.prospect import Prospect
from app.models.research_request import ResearchRequest
from app.models.research_template import ResearchTemplate
from app.models.user import User
from app.research.pipeline import RESEARCH_REQUEST_RUN_REQUESTED_EVENT_TYPE
from app.schemas.research_request import (
    ResearchRequestCreate,
    ResearchRequestRead,
    ResearchRequestRunBody,
    ResearchRequestRunQueued,
)
from app.workflow_engine.events import publish_event

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
    response_model=ResearchRequestRunQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_research_request_endpoint(
    prospect_id: uuid.UUID,
    request_id: uuid.UUID,
    run_in: ResearchRequestRunBody | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResearchRequestRunQueued:
    """
    M8.10: no longer runs synchronously in-request - exact mirror of
    Discovery's M8.8 change (see app/api/routes/discovery_searches.py's
    run_search() docstring for the full reasoning). This endpoint now only
    validates the request and publishes
    RESEARCH_REQUEST_RUN_REQUESTED_EVENT_TYPE (subject_type=
    "research_request", subject_id=request.id, actor_type="user",
    actor_id=str(current_user.id)). `run_in` (the per-run input the
    manual_document provider needs, since ResearchRequest has no
    persisted source_spec of its own) is carried in the event's payload -
    ResearchExecutionAction reads it back out from there (see that
    module's own docstring).

    The real execution happens asynchronously via the
    "research_request_execution" WorkflowDefinition (app/workflow_bootstrap.py).
    The frontend finds the resulting job by polling
    GET .../research-jobs?research_request_id={request_id}.
    """
    request = _get_request_or_404(db, profile.id, prospect_id, request_id)
    run_input = run_in.model_dump(exclude_none=True) if run_in is not None else None

    publish_event(
        db,
        event_type=RESEARCH_REQUEST_RUN_REQUESTED_EVENT_TYPE,
        company_profile_id=profile.id,
        source="app.api.routes.research_requests",
        subject_type="research_request",
        subject_id=request.id,
        payload={"run_input": run_input} if run_input else None,
        actor_type="user",
        actor_id=str(current_user.id),
    )
    db.commit()

    return ResearchRequestRunQueued(status="queued", research_request_id=request.id)
