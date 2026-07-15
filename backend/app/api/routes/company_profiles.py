import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.industry import Industry
from app.models.user import User
from app.schemas.company_profile import CompanyProfileCreate, CompanyProfileRead, CompanyProfileUpdate

router = APIRouter()

# CompanyProfile is deliberately NOT a singleton: a user can own multiple
# businesses and switch between them. Every profile is scoped to its owner
# via get_owned_company_profile (shared with products/icp-criteria/
# knowledge-base routes nested under this one).


def _set_industries(db: Session, profile: CompanyProfile, industry_ids: list[uuid.UUID]) -> None:
    if not industry_ids:
        profile.industries = []
        return
    industries = db.scalars(select(Industry).where(Industry.id.in_(industry_ids))).all()
    found_ids = {i.id for i in industries}
    missing = set(industry_ids) - found_ids
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown industry id(s): {missing}")
    profile.industries = list(industries)


def _clear_other_defaults(db: Session, owner_user_id: uuid.UUID, keep_profile_id: uuid.UUID | None) -> None:
    """
    Enforce "at most one default CompanyProfile per user" at the application
    layer (there's no partial-unique-index in the DB for this, so it has to
    be maintained here, atomically within the same transaction as the write
    that sets the new default). Unsets is_default on every other profile
    this user owns; keep_profile_id (the profile just being created/updated)
    is left untouched since it's about to be set to True by the caller.
    """
    stmt = select(CompanyProfile).where(
        CompanyProfile.owner_user_id == owner_user_id,
        CompanyProfile.is_default.is_(True),
    )
    if keep_profile_id is not None:
        stmt = stmt.where(CompanyProfile.id != keep_profile_id)
    for other in db.scalars(stmt).all():
        other.is_default = False


@router.get("/company-profiles", response_model=list[CompanyProfileRead])
def list_company_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CompanyProfile]:
    stmt = select(CompanyProfile).where(CompanyProfile.owner_user_id == current_user.id).order_by(CompanyProfile.created_at.asc())
    return list(db.scalars(stmt).all())


@router.post("/company-profiles", response_model=CompanyProfileRead, status_code=status.HTTP_201_CREATED)
def create_company_profile(
    profile_in: CompanyProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CompanyProfile:
    data = profile_in.model_dump(exclude={"industry_ids"})
    profile = CompanyProfile(owner_user_id=current_user.id, **data)
    db.add(profile)
    db.flush()  # assign an id before attaching the industries relationship
    _set_industries(db, profile, profile_in.industry_ids)
    if profile.is_default:
        _clear_other_defaults(db, current_user.id, keep_profile_id=profile.id)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/company-profiles/{company_profile_id}", response_model=CompanyProfileRead)
def get_company_profile(
    profile: CompanyProfile = Depends(get_owned_company_profile),
) -> CompanyProfile:
    return profile


@router.put("/company-profiles/{company_profile_id}", response_model=CompanyProfileRead)
def update_company_profile(
    profile_in: CompanyProfileUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> CompanyProfile:
    data = profile_in.model_dump(exclude={"industry_ids"}, exclude_unset=True)
    for field, value in data.items():
        setattr(profile, field, value)
    if profile_in.industry_ids is not None:
        _set_industries(db, profile, profile_in.industry_ids)
    if "is_default" in data and profile.is_default:
        _clear_other_defaults(db, profile.owner_user_id, keep_profile_id=profile.id)
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/company-profiles/{company_profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company_profile(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> None:
    # Cascades to this profile's products, ICP criteria, and knowledge base
    # entries (see the cascade="all, delete-orphan" relationships on the model).
    db.delete(profile)
    db.commit()
