import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_owned_company_profile
from app.models.company_profile import CompanyProfile
from app.models.intelligence_snapshot import IntelligenceSnapshot
from app.models.prospect import Prospect
from app.db.session import get_db
from app.schemas.intelligence_snapshot import IntelligenceSnapshotRead

router = APIRouter()

# Read-only - IntelligenceSnapshots are written exactly once, by the
# pipeline, and never edited after creation (see the model's docstring).
# Comparing "previous vs current research" means reading two rows here,
# never mutating one.


def _get_prospect_or_404(db: Session, profile_id: uuid.UUID, prospect_id: uuid.UUID) -> Prospect:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None or prospect.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return prospect


def _snapshot_options():
    return (selectinload(IntelligenceSnapshot.signals), selectinload(IntelligenceSnapshot.recommendations))


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/intelligence-snapshots",
    response_model=list[IntelligenceSnapshotRead],
)
def list_intelligence_snapshots(
    prospect_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[IntelligenceSnapshot]:
    _get_prospect_or_404(db, profile.id, prospect_id)
    stmt = (
        select(IntelligenceSnapshot)
        .where(IntelligenceSnapshot.prospect_id == prospect_id)
        .options(*_snapshot_options())
        .order_by(IntelligenceSnapshot.version.desc())
    )
    return list(db.scalars(stmt).all())


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/intelligence-snapshots/current",
    response_model=IntelligenceSnapshotRead,
)
def get_current_intelligence_snapshot(
    prospect_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> IntelligenceSnapshot:
    _get_prospect_or_404(db, profile.id, prospect_id)
    stmt = (
        select(IntelligenceSnapshot)
        .where(IntelligenceSnapshot.prospect_id == prospect_id, IntelligenceSnapshot.is_current.is_(True))
        .options(*_snapshot_options())
    )
    snapshot = db.scalars(stmt).first()
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No intelligence snapshot exists yet for this prospect")
    return snapshot


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/intelligence-snapshots/{snapshot_id}",
    response_model=IntelligenceSnapshotRead,
)
def get_intelligence_snapshot(
    prospect_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> IntelligenceSnapshot:
    _get_prospect_or_404(db, profile.id, prospect_id)
    stmt = select(IntelligenceSnapshot).where(IntelligenceSnapshot.id == snapshot_id).options(*_snapshot_options())
    snapshot = db.scalars(stmt).first()
    if snapshot is None or snapshot.prospect_id != prospect_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intelligence snapshot not found")
    return snapshot
