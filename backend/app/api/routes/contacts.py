import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.company import Company
from app.models.contact import Contact
from app.models.user import User
from app.schemas.contact import ContactCreate, ContactRead

router = APIRouter()

# Same minimal M0 scope as companies.py: manual create/list only, to prove
# the CRM schema's read/write path end-to-end. Automated contact discovery
# (finding purchasing contacts on a company's site) became ProspectContact
# starting M1, not anything added to this file.
#
# DEPRECATED - Phase 1, same status/reasoning as companies.py. Routes kept
# working exactly as-is; marked deprecated=True so new development doesn't
# get built against this model. Do not extend; use ProspectContact
# instead. See Contact's own model docstring and
# deferred-items-and-design-boundaries.md.


@router.get("/contacts", response_model=list[ContactRead], deprecated=True)
def list_contacts(
    company_id: uuid.UUID | None = Query(None, description="Filter to a single company"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Contact]:
    stmt = select(Contact).order_by(Contact.created_at.desc())
    if company_id is not None:
        stmt = stmt.where(Contact.company_id == company_id)
    stmt = stmt.offset(skip).limit(limit)
    return list(db.scalars(stmt).all())


@router.post("/contacts", response_model=ContactRead, status_code=status.HTTP_201_CREATED, deprecated=True)
def create_contact(
    contact_in: ContactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Contact:
    company = db.get(Company, contact_in.company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    contact = Contact(**contact_in.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.get("/contacts/{contact_id}", response_model=ContactRead, deprecated=True)
def get_contact(
    contact_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact
