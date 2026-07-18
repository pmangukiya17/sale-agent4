"""
SendingProfile CRUD - plain mutable-in-place configuration, same
convention as Product/ICPCriteria (see SendingProfile's model docstring).
Deliberately does NOT touch ProviderConnection/ProviderCredential - which
mailbox a profile sends through is changed via provider_connection_id on
SendingProfileUpdate (a plain FK swap to an already-Connected connection),
never through these routes directly; establishing a NEW connection is the
OAuth lifecycle in provider_connections.py.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.provider_connection import ProviderConnection
from app.models.sending_profile import SendingProfile
from app.schemas.sending_profile import SendingProfileCreate, SendingProfileRead, SendingProfileUpdate

router = APIRouter()


def _validate_provider_connection(
    db: Session, profile_id: uuid.UUID, connection_id: uuid.UUID | None, expected_provider_key: str
) -> None:
    """Also cross-checks connection.provider_key == expected_provider_key -
    a gap noticed while planning Layer 6: dispatch_service resolves the
    actual provider implementation from the CONNECTION's provider_key
    (see dispatch_service.py), not the SendingProfile's, so attaching a
    mismatched connection wouldn't break sending, but would leave a
    profile silently labeled "outlook" while genuinely sending through a
    Gmail mailbox - exactly the kind of quiet inconsistency worth
    rejecting at the API boundary rather than letting the frontend work
    around it."""
    if connection_id is None:
        return
    connection = db.get(ProviderConnection, connection_id)
    if connection is None or connection.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown provider_connection_id for this business")
    if connection.provider_key != expected_provider_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This connection is a '{connection.provider_key}' mailbox and can't be attached to a "
            f"'{expected_provider_key}' sending profile.",
        )


@router.get("/company-profiles/{company_profile_id}/sending-profiles", response_model=list[SendingProfileRead])
def list_sending_profiles(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[SendingProfile]:
    stmt = select(SendingProfile).where(SendingProfile.company_profile_id == profile.id).order_by(SendingProfile.created_at.desc())
    return list(db.scalars(stmt).all())


@router.post(
    "/company-profiles/{company_profile_id}/sending-profiles",
    response_model=SendingProfileRead,
    status_code=status.HTTP_201_CREATED,
)
def create_sending_profile(
    profile_in: SendingProfileCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> SendingProfile:
    _validate_provider_connection(db, profile.id, profile_in.provider_connection_id, profile_in.provider_key)
    sending_profile = SendingProfile(company_profile_id=profile.id, **profile_in.model_dump())
    db.add(sending_profile)
    db.commit()
    db.refresh(sending_profile)
    return sending_profile


def _get_sending_profile_or_404(db: Session, profile_id: uuid.UUID, sending_profile_id: uuid.UUID) -> SendingProfile:
    sending_profile = db.get(SendingProfile, sending_profile_id)
    if sending_profile is None or sending_profile.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sending profile not found")
    return sending_profile


@router.get("/company-profiles/{company_profile_id}/sending-profiles/{sending_profile_id}", response_model=SendingProfileRead)
def get_sending_profile(
    sending_profile_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> SendingProfile:
    return _get_sending_profile_or_404(db, profile.id, sending_profile_id)


@router.put("/company-profiles/{company_profile_id}/sending-profiles/{sending_profile_id}", response_model=SendingProfileRead)
def update_sending_profile(
    sending_profile_id: uuid.UUID,
    profile_in: SendingProfileUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> SendingProfile:
    sending_profile = _get_sending_profile_or_404(db, profile.id, sending_profile_id)
    update_data = profile_in.model_dump(exclude_unset=True)
    if "provider_connection_id" in update_data:
        # provider_key itself is never in update_data - SendingProfileUpdate
        # deliberately doesn't accept it (see its docstring) - so the
        # cross-check is always against the row's existing, unchanged
        # provider_key.
        _validate_provider_connection(db, profile.id, update_data["provider_connection_id"], sending_profile.provider_key)
    for field, value in update_data.items():
        setattr(sending_profile, field, value)
    db.commit()
    db.refresh(sending_profile)
    return sending_profile


@router.delete("/company-profiles/{company_profile_id}/sending-profiles/{sending_profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sending_profile(
    sending_profile_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> None:
    sending_profile = _get_sending_profile_or_404(db, profile.id, sending_profile_id)
    db.delete(sending_profile)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This sending profile is used by at least one delivery campaign and can't be deleted while in use.",
        )
