import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseRead, KnowledgeBaseUpdate

router = APIRouter()


@router.get("/company-profiles/{company_profile_id}/knowledge-base", response_model=list[KnowledgeBaseRead])
def list_knowledge_base(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[KnowledgeBase]:
    stmt = (
        select(KnowledgeBase)
        .where(KnowledgeBase.company_profile_id == profile.id)
        .order_by(KnowledgeBase.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("/company-profiles/{company_profile_id}/knowledge-base", response_model=KnowledgeBaseRead, status_code=status.HTTP_201_CREATED)
def create_knowledge_base_entry(
    entry_in: KnowledgeBaseCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    entry = KnowledgeBase(company_profile_id=profile.id, **entry_in.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _get_entry_or_404(db: Session, profile_id: uuid.UUID, entry_id: uuid.UUID) -> KnowledgeBase:
    entry = db.get(KnowledgeBase, entry_id)
    if entry is None or entry.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base entry not found")
    return entry


@router.get("/company-profiles/{company_profile_id}/knowledge-base/{entry_id}", response_model=KnowledgeBaseRead)
def get_knowledge_base_entry(
    entry_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    return _get_entry_or_404(db, profile.id, entry_id)


@router.put("/company-profiles/{company_profile_id}/knowledge-base/{entry_id}", response_model=KnowledgeBaseRead)
def update_knowledge_base_entry(
    entry_id: uuid.UUID,
    entry_in: KnowledgeBaseUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    entry = _get_entry_or_404(db, profile.id, entry_id)
    for field, value in entry_in.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/company-profiles/{company_profile_id}/knowledge-base/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base_entry(
    entry_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> None:
    entry = _get_entry_or_404(db, profile.id, entry_id)
    db.delete(entry)
    db.commit()
