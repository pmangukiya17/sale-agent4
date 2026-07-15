import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.enums import ProspectStatus
from app.models.prospect import Prospect
from app.models.prospect_timeline_event import ProspectTimelineEvent
from app.models.user import User
from app.schemas.prospect import ProspectRead, ProspectRejectRequest, ProspectUpdate

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _prospect_options():
    return (selectinload(Prospect.contacts), selectinload(Prospect.sources))


@router.get("/company-profiles/{company_profile_id}/prospects", response_model=list[ProspectRead])
def list_prospects(
    status_filter: ProspectStatus | None = Query(None, alias="status"),
    discovery_search_id: uuid.UUID | None = Query(None),
    buyer_type_id: uuid.UUID | None = Query(None),
    country: str | None = Query(None),
    min_score: float | None = Query(None),
    potential_duplicate: bool | None = Query(None),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[Prospect]:
    stmt = select(Prospect).where(Prospect.company_profile_id == profile.id).options(*_prospect_options())
    if status_filter is not None:
        stmt = stmt.where(Prospect.status == status_filter)
    if discovery_search_id is not None:
        stmt = stmt.where(Prospect.discovery_search_id == discovery_search_id)
    if buyer_type_id is not None:
        stmt = stmt.where(Prospect.buyer_type_id == buyer_type_id)
    if country is not None:
        stmt = stmt.where(Prospect.country == country)
    if min_score is not None:
        stmt = stmt.where(Prospect.total_score >= min_score)
    if potential_duplicate is not None:
        if potential_duplicate:
            stmt = stmt.where(Prospect.potential_duplicate_of_prospect_id.is_not(None))
        else:
            stmt = stmt.where(Prospect.potential_duplicate_of_prospect_id.is_(None))
    stmt = stmt.order_by(Prospect.total_score.desc().nulls_last(), Prospect.first_discovered_at.desc())
    return list(db.scalars(stmt).all())


def _get_prospect_or_404(db: Session, profile_id: uuid.UUID, prospect_id: uuid.UUID) -> Prospect:
    stmt = select(Prospect).where(Prospect.id == prospect_id).options(*_prospect_options())
    prospect = db.scalars(stmt).first()
    if prospect is None or prospect.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return prospect


@router.get("/company-profiles/{company_profile_id}/prospects/{prospect_id}", response_model=ProspectRead)
def get_prospect(
    prospect_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Prospect:
    return _get_prospect_or_404(db, profile.id, prospect_id)


@router.put("/company-profiles/{company_profile_id}/prospects/{prospect_id}", response_model=ProspectRead)
def update_prospect(
    prospect_id: uuid.UUID,
    prospect_in: ProspectUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Prospect:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    for field, value in prospect_in.model_dump(exclude_unset=True).items():
        setattr(prospect, field, value)
    db.add(ProspectTimelineEvent(prospect_id=prospect.id, event_type="manually_edited", actor="system"))
    db.commit()
    db.refresh(prospect)
    return prospect


@router.post("/company-profiles/{company_profile_id}/prospects/{prospect_id}/approve", response_model=ProspectRead)
def approve_prospect(
    prospect_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Prospect:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    prospect.status = ProspectStatus.APPROVED
    prospect.reviewed_by_user_id = current_user.id
    prospect.reviewed_at = _now()
    db.add(ProspectTimelineEvent(
        prospect_id=prospect.id, event_type="approved", actor=f"user:{current_user.id}",
    ))
    db.commit()
    db.refresh(prospect)
    return prospect


@router.post("/company-profiles/{company_profile_id}/prospects/{prospect_id}/reject", response_model=ProspectRead)
def reject_prospect(
    prospect_id: uuid.UUID,
    reject_in: ProspectRejectRequest,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Prospect:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    prospect.status = ProspectStatus.REJECTED
    prospect.rejection_reason = reject_in.rejection_reason
    prospect.reviewed_by_user_id = current_user.id
    prospect.reviewed_at = _now()
    db.add(ProspectTimelineEvent(
        prospect_id=prospect.id, event_type="rejected", actor=f"user:{current_user.id}",
        payload={"rejection_reason": reject_in.rejection_reason},
    ))
    db.commit()
    db.refresh(prospect)
    return prospect


@router.post("/company-profiles/{company_profile_id}/prospects/{prospect_id}/archive", response_model=ProspectRead)
def archive_prospect(
    prospect_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Prospect:
    prospect = _get_prospect_or_404(db, profile.id, prospect_id)
    prospect.status = ProspectStatus.ARCHIVED
    prospect.reviewed_by_user_id = current_user.id
    prospect.reviewed_at = _now()
    db.add(ProspectTimelineEvent(
        prospect_id=prospect.id, event_type="archived", actor=f"user:{current_user.id}",
    ))
    db.commit()
    db.refresh(prospect)
    return prospect
