import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.personalization_snapshot import PersonalizationSnapshot
from app.models.personalization_strategy import PersonalizationStrategy
from app.models.prospect import Prospect
from app.schemas.personalization_snapshot import PersonalizationSnapshotRead

router = APIRouter()

# Read-only - PersonalizationSnapshots are written exactly once, by the
# pipeline, and never edited after creation (see the model's docstring).
# Comparing "how has our strategy for this buyer evolved" means reading
# multiple rows here, never mutating one.


def _get_prospect_or_404(db: Session, profile_id: uuid.UUID, prospect_id: uuid.UUID) -> Prospect:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None or prospect.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return prospect


def _snapshot_options():
    return (
        selectinload(PersonalizationSnapshot.communication_strategy),
        selectinload(PersonalizationSnapshot.strategies).selectinload(PersonalizationStrategy.evidence),
    )


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/personalization-snapshots",
    response_model=list[PersonalizationSnapshotRead],
)
def list_personalization_snapshots(
    prospect_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[PersonalizationSnapshot]:
    _get_prospect_or_404(db, profile.id, prospect_id)
    stmt = (
        select(PersonalizationSnapshot)
        .where(PersonalizationSnapshot.prospect_id == prospect_id)
        .options(*_snapshot_options())
        .order_by(PersonalizationSnapshot.version.desc())
    )
    return list(db.scalars(stmt).all())


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/personalization-snapshots/current",
    response_model=PersonalizationSnapshotRead,
)
def get_current_personalization_snapshot(
    prospect_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> PersonalizationSnapshot:
    _get_prospect_or_404(db, profile.id, prospect_id)
    stmt = (
        select(PersonalizationSnapshot)
        .where(PersonalizationSnapshot.prospect_id == prospect_id, PersonalizationSnapshot.is_current.is_(True))
        .options(*_snapshot_options())
    )
    snapshot = db.scalars(stmt).first()
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No personalization snapshot exists yet for this prospect")
    return snapshot


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/personalization-snapshots/{snapshot_id}",
    response_model=PersonalizationSnapshotRead,
)
def get_personalization_snapshot(
    prospect_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> PersonalizationSnapshot:
    _get_prospect_or_404(db, profile.id, prospect_id)
    stmt = select(PersonalizationSnapshot).where(PersonalizationSnapshot.id == snapshot_id).options(*_snapshot_options())
    snapshot = db.scalars(stmt).first()
    if snapshot is None or snapshot.prospect_id != prospect_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Personalization snapshot not found")
    return snapshot
