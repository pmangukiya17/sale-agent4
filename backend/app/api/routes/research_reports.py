import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.intelligence_snapshot import IntelligenceSnapshot
from app.models.prospect import Prospect
from app.models.research_report import ResearchReport
from app.research.reporting import generate_research_report
from app.schemas.research_report import ResearchReportRead

router = APIRouter()


class GenerateReportBody(BaseModel):
    # If omitted, generates from the prospect's current (is_current=True)
    # IntelligenceSnapshot.
    intelligence_snapshot_id: uuid.UUID | None = None


def _get_prospect_or_404(db: Session, profile_id: uuid.UUID, prospect_id: uuid.UUID) -> Prospect:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None or prospect.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return prospect


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/research-reports",
    response_model=list[ResearchReportRead],
)
def list_research_reports(
    prospect_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[ResearchReport]:
    _get_prospect_or_404(db, profile.id, prospect_id)
    stmt = (
        select(ResearchReport)
        .where(ResearchReport.prospect_id == prospect_id)
        .order_by(ResearchReport.generated_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/research-reports/{report_id}",
    response_model=ResearchReportRead,
)
def get_research_report(
    prospect_id: uuid.UUID,
    report_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ResearchReport:
    _get_prospect_or_404(db, profile.id, prospect_id)
    report = db.get(ResearchReport, report_id)
    if report is None or report.prospect_id != prospect_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research report not found")
    return report


@router.post(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/research-reports/generate",
    response_model=ResearchReportRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_report(
    prospect_id: uuid.UUID,
    body: GenerateReportBody | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ResearchReport:
    """
    Generates a new ResearchReport FROM an already-stored
    IntelligenceSnapshot - never an independent source of truth (per the
    approved M2 adjustment). Regenerating creates a new row; it never
    edits a previous report.
    """
    _get_prospect_or_404(db, profile.id, prospect_id)

    if body is not None and body.intelligence_snapshot_id is not None:
        snapshot = db.get(IntelligenceSnapshot, body.intelligence_snapshot_id)
        if snapshot is None or snapshot.prospect_id != prospect_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown intelligence_snapshot_id")
    else:
        stmt = select(IntelligenceSnapshot).where(
            IntelligenceSnapshot.prospect_id == prospect_id, IntelligenceSnapshot.is_current.is_(True)
        )
        snapshot = db.scalars(stmt).first()
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No intelligence snapshot exists yet for this prospect - run research first.",
            )

    return generate_research_report(db, snapshot)
