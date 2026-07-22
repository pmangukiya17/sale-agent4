import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.user import User
from app.schemas.prospect_contact import ProspectContactCreate, ProspectContactRead, ProspectContactUpdate

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_prospect_or_404(db: Session, profile_id: uuid.UUID, prospect_id: uuid.UUID) -> Prospect:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None or prospect.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return prospect


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts",
    response_model=list[ProspectContactRead],
)
def list_prospect_contacts(
    prospect_id: uuid.UUID,
    include_archived: bool = Query(False),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[ProspectContact]:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    stmt = select(ProspectContact).where(ProspectContact.prospect_id == prospect.id)
    if not include_archived:
        # Platform-wide lifecycle rule: archived contacts are hidden from
        # list views by default (see
        # deferred-items-and-design-boundaries.md). Callers that need
        # them (e.g. an "Archived" tab) pass ?include_archived=true.
        stmt = stmt.where(ProspectContact.is_archived.is_(False))
    stmt = stmt.order_by(ProspectContact.created_at)
    return list(db.scalars(stmt).all())


@router.post(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts",
    response_model=ProspectContactRead,
    status_code=status.HTTP_201_CREATED,
)
def create_prospect_contact(
    prospect_id: uuid.UUID,
    contact_in: ProspectContactCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ProspectContact:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    contact = ProspectContact(prospect_id=prospect.id, **contact_in.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def _get_contact_or_404(db: Session, prospect_id: uuid.UUID, contact_id: uuid.UUID) -> ProspectContact:
    contact = db.get(ProspectContact, contact_id)
    if contact is None or contact.prospect_id != prospect_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect contact not found")
    return contact


@router.put(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}",
    response_model=ProspectContactRead,
)
def update_prospect_contact(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    contact_in: ProspectContactUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ProspectContact:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    contact = _get_contact_or_404(db, prospect.id, contact_id)
    for field, value in contact_in.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    db.commit()
    db.refresh(contact)
    return contact


@router.post(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}/archive",
    response_model=ProspectContactRead,
)
def archive_prospect_contact(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProspectContact:
    """
    The preferred way to remove a contact from active use: preserves the
    row (and therefore all of its RESTRICT-protected execution history)
    while hiding it from list_prospect_contacts by default. Mirrors
    Prospect.archive's pattern of recording who archived it and when.
    """
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    contact = _get_contact_or_404(db, prospect.id, contact_id)
    contact.is_archived = True
    contact.archived_at = _now()
    contact.archived_by_user_id = current_user.id
    db.commit()
    db.refresh(contact)
    return contact


@router.post(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}/unarchive",
    response_model=ProspectContactRead,
)
def unarchive_prospect_contact(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ProspectContact:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    contact = _get_contact_or_404(db, prospect.id, contact_id)
    contact.is_archived = False
    contact.archived_at = None
    contact.archived_by_user_id = None
    db.commit()
    db.refresh(contact)
    return contact


@router.delete(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_prospect_contact(
    prospect_id: uuid.UUID,
    contact_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> None:
    # Hard delete only remains safe for contacts with zero execution
    # history (RESTRICT on delivery_queue_items/outreach_* now enforces
    # this at the DB level). A dedicated archive lifecycle - the
    # preferred path for contacts that do have history, matching
    # Prospect's approve/reject/archive pattern - is tracked as a
    # follow-up; see deferred-items-and-design-boundaries.md.
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    contact = _get_contact_or_404(db, prospect.id, contact_id)
    db.delete(contact)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This contact has outreach/delivery history and can't be hard-deleted. "
            "Archive it instead once archiving is available.",
        )
