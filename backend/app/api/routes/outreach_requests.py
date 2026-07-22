import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.outreach_playbook import OutreachPlaybook
from app.models.outreach_request import OutreachRequest
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.user import User
from app.outreach.pipeline import OUTREACH_REQUEST_RUN_REQUESTED_EVENT_TYPE
from app.schemas.outreach_request import (
    OutreachRequestCreate,
    OutreachRequestRead,
    OutreachRequestRunBody,
    OutreachRequestRunQueued,
)
from app.workflow_engine.events import publish_event

router = APIRouter()


def _get_prospect_or_404(db: Session, profile_id: uuid.UUID, prospect_id: uuid.UUID) -> Prospect:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None or prospect.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return prospect


def _get_contact_or_404(db: Session, prospect_id: uuid.UUID, contact_id: uuid.UUID) -> ProspectContact:
    contact = db.get(ProspectContact, contact_id)
    if contact is None or contact.prospect_id != prospect_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect contact not found")
    return contact


def _validate_playbook(db: Session, profile_id: uuid.UUID, playbook_id: uuid.UUID) -> None:
    playbook = db.get(OutreachPlaybook, playbook_id)
    if playbook is None or (playbook.company_profile_id != profile_id and not playbook.is_system_default):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown outreach_playbook_id")


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-requests",
    response_model=list[OutreachRequestRead],
)
def list_outreach_requests(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[OutreachRequest]:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    _get_contact_or_404(db, prospect.id, contact_id)
    stmt = (
        select(OutreachRequest)
        .where(OutreachRequest.prospect_contact_id == contact_id)
        .order_by(OutreachRequest.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-requests",
    response_model=OutreachRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_outreach_request(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    request_in: OutreachRequestCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutreachRequest:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    _get_contact_or_404(db, prospect.id, contact_id)
    _validate_playbook(db, profile.id, request_in.outreach_playbook_id)
    request = OutreachRequest(
        prospect_id=prospect_id,
        prospect_contact_id=contact_id,
        company_profile_id=profile.id,
        requested_by_user_id=current_user.id,
        **request_in.model_dump(),
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def _get_request_or_404(db: Session, contact_id: uuid.UUID, request_id: uuid.UUID) -> OutreachRequest:
    request = db.get(OutreachRequest, request_id)
    if request is None or request.prospect_contact_id != contact_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outreach request not found")
    return request


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-requests/{request_id}",
    response_model=OutreachRequestRead,
)
def get_outreach_request(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    request_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> OutreachRequest:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    _get_contact_or_404(db, prospect.id, contact_id)
    return _get_request_or_404(db, contact_id, request_id)


@router.post(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-requests/{request_id}/run",
    response_model=OutreachRequestRunQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_outreach_request_endpoint(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    request_id: uuid.UUID,
    run_in: OutreachRequestRunBody | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutreachRequestRunQueued:
    """
    M8.15: no longer runs synchronously in-request - mirrors Discovery's
    (M8.8), Research's (M8.13), and Personalization's (M8.14) identical
    change. This endpoint only validates the request and publishes
    OUTREACH_REQUEST_RUN_REQUESTED_EVENT_TYPE (subject_type=
    "outreach_request", subject_id=request.id, actor_type="user",
    actor_id=str(current_user.id)). Outreach has no per-run external
    input either - `run_in` remains the same unused placeholder it
    already was on the synchronous path (see OutreachRequestRunBody's own
    docstring).

    The real execution happens asynchronously via the
    "outreach_request_execution" WorkflowDefinition: renders one new
    versioned OutreachDraft for this (prospect_contact, channel) pair from
    the current PersonalizationSnapshot and the request's OutreachPlaybook
    - never sends anything, never touches CRM Company/Contact/Thread/
    Message (see the pipeline's docstring for why that stays deferred).
    The frontend finds the resulting job by polling
    GET .../outreach-jobs?outreach_request_id={request_id}.
    """
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    _get_contact_or_404(db, prospect.id, contact_id)
    request = _get_request_or_404(db, contact_id, request_id)

    publish_event(
        db,
        event_type=OUTREACH_REQUEST_RUN_REQUESTED_EVENT_TYPE,
        company_profile_id=profile.id,
        source="app.api.routes.outreach_requests",
        subject_type="outreach_request",
        subject_id=request.id,
        actor_type="user",
        actor_id=str(current_user.id),
    )
    db.commit()

    return OutreachRequestRunQueued(status="queued", outreach_request_id=request.id)
