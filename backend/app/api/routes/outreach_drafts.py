import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.outreach_draft import OutreachDraft
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.user import User
from app.outreach.pipeline import approve_outreach_draft, edit_outreach_draft, reject_outreach_draft
from app.schemas.outreach_draft import (
    OutreachDraftApproveBody,
    OutreachDraftEditBody,
    OutreachDraftRead,
    OutreachDraftRejectBody,
)

router = APIRouter()

# OutreachDrafts are produced exactly once per run by the pipeline (see
# app.outreach.pipeline.run_outreach_request) - these routes never create
# one directly. Approve/reject/edit are the only write actions here, and
# each is deliberately narrow: approve/reject only change status/metadata,
# edit only ever touches current_content (logged via a child OutreachEdit
# row) - ai_generated_content is never reachable through any route.


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


def _draft_options():
    return (selectinload(OutreachDraft.evidence), selectinload(OutreachDraft.edits))


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-drafts",
    response_model=list[OutreachDraftRead],
)
def list_outreach_drafts(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    channel_key: str | None = Query(None),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[OutreachDraft]:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    _get_contact_or_404(db, prospect.id, contact_id)
    stmt = (
        select(OutreachDraft)
        .where(OutreachDraft.prospect_contact_id == contact_id)
        .options(*_draft_options())
        .order_by(OutreachDraft.channel_key, OutreachDraft.version.desc())
    )
    if channel_key is not None:
        stmt = stmt.where(OutreachDraft.channel_key == channel_key)
    return list(db.scalars(stmt).all())


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-drafts/current",
    response_model=OutreachDraftRead,
)
def get_current_outreach_draft(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    channel_key: str = Query(...),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> OutreachDraft:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    _get_contact_or_404(db, prospect.id, contact_id)
    stmt = (
        select(OutreachDraft)
        .where(
            OutreachDraft.prospect_contact_id == contact_id,
            OutreachDraft.channel_key == channel_key,
            OutreachDraft.is_current.is_(True),
        )
        .options(*_draft_options())
    )
    draft = db.scalars(stmt).first()
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No current outreach draft exists yet for channel '{channel_key}' and this contact",
        )
    return draft


def _get_draft_or_404(db: Session, contact_id: uuid.UUID, draft_id: uuid.UUID) -> OutreachDraft:
    stmt = select(OutreachDraft).where(OutreachDraft.id == draft_id).options(*_draft_options())
    draft = db.scalars(stmt).first()
    if draft is None or draft.prospect_contact_id != contact_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outreach draft not found")
    return draft


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-drafts/{draft_id}",
    response_model=OutreachDraftRead,
)
def get_outreach_draft(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    draft_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> OutreachDraft:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    _get_contact_or_404(db, prospect.id, contact_id)
    return _get_draft_or_404(db, contact_id, draft_id)


@router.post(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-drafts/{draft_id}/approve",
    response_model=OutreachDraftRead,
)
def approve_outreach_draft_endpoint(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    draft_id: uuid.UUID,
    _body: OutreachDraftApproveBody | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutreachDraft:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    _get_contact_or_404(db, prospect.id, contact_id)
    draft = _get_draft_or_404(db, contact_id, draft_id)
    return approve_outreach_draft(db, draft, current_user)


@router.post(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-drafts/{draft_id}/reject",
    response_model=OutreachDraftRead,
)
def reject_outreach_draft_endpoint(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: OutreachDraftRejectBody,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> OutreachDraft:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    _get_contact_or_404(db, prospect.id, contact_id)
    draft = _get_draft_or_404(db, contact_id, draft_id)
    return reject_outreach_draft(db, draft, body.reason)


@router.post(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-drafts/{draft_id}/edit",
    response_model=OutreachDraftRead,
)
def edit_outreach_draft_endpoint(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: OutreachDraftEditBody,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutreachDraft:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    _get_contact_or_404(db, prospect.id, contact_id)
    draft = _get_draft_or_404(db, contact_id, draft_id)
    return edit_outreach_draft(db, draft, body.new_content, current_user, body.edit_reason)
