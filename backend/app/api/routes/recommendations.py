import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.enums import RecommendationStatus, RecommendationType
from app.models.prospect import Prospect
from app.models.recommendation import Recommendation
from app.schemas.recommendation import RecommendationPortfolioRead, RecommendationRead, RecommendationUpdate

router = APIRouter()


def _get_prospect_or_404(db: Session, profile_id: uuid.UUID, prospect_id: uuid.UUID) -> Prospect:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None or prospect.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return prospect


@router.get(
    "/company-profiles/{company_profile_id}/recommendations",
    response_model=list[RecommendationPortfolioRead],
)
def list_portfolio_recommendations(
    status_filter: RecommendationStatus | None = Query(None, alias="status"),
    recommendation_type: RecommendationType | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[Recommendation]:
    """Track C2 (dashboard-capabilities-architecture-plan.md): the AI
    Recommendations dashboard widget needs recommendations across a
    business's entire portfolio of prospects, not one prospect at a time -
    this is the only genuinely new endpoint C2 adds. Everything else
    (the Recommendation model, evidence, status transitions) already
    existed from the per-prospect routes above and is reused unchanged.

    Tenant isolation is enforced by joining through Prospect and filtering
    on Prospect.company_profile_id, the same pattern every other
    cross-portfolio endpoint in this codebase uses (e.g. the Discovery
    portfolio views) - a recommendation can never leak across businesses
    because it is only reachable via a prospect that itself belongs to
    the caller's own profile.
    """
    stmt = (
        select(Recommendation)
        .join(Prospect, Recommendation.prospect_id == Prospect.id)
        .where(Prospect.company_profile_id == profile.id)
        .options(selectinload(Recommendation.evidence), selectinload(Recommendation.prospect))
        .order_by(Recommendation.created_at.desc())
        .limit(limit)
    )
    if status_filter is not None:
        stmt = stmt.where(Recommendation.status == status_filter)
    if recommendation_type is not None:
        stmt = stmt.where(Recommendation.recommendation_type == recommendation_type)
    return list(db.scalars(stmt).all())


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/recommendations",
    response_model=list[RecommendationRead],
)
def list_recommendations(
    prospect_id: uuid.UUID,
    status_filter: RecommendationStatus | None = Query(None, alias="status"),
    recommendation_type: RecommendationType | None = Query(None),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[Recommendation]:
    _get_prospect_or_404(db, profile.id, prospect_id)
    stmt = (
        select(Recommendation)
        .where(Recommendation.prospect_id == prospect_id)
        .options(selectinload(Recommendation.evidence))
        .order_by(Recommendation.created_at.desc())
    )
    if status_filter is not None:
        stmt = stmt.where(Recommendation.status == status_filter)
    if recommendation_type is not None:
        stmt = stmt.where(Recommendation.recommendation_type == recommendation_type)
    return list(db.scalars(stmt).all())


def _get_recommendation_or_404(db: Session, prospect_id: uuid.UUID, recommendation_id: uuid.UUID) -> Recommendation:
    stmt = select(Recommendation).where(Recommendation.id == recommendation_id).options(selectinload(Recommendation.evidence))
    recommendation = db.scalars(stmt).first()
    if recommendation is None or recommendation.prospect_id != prospect_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    return recommendation


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/recommendations/{recommendation_id}",
    response_model=RecommendationRead,
)
def get_recommendation(
    prospect_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Recommendation:
    _get_prospect_or_404(db, profile.id, prospect_id)
    return _get_recommendation_or_404(db, prospect_id, recommendation_id)


@router.put(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/recommendations/{recommendation_id}",
    response_model=RecommendationRead,
)
def update_recommendation(
    prospect_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    recommendation_in: RecommendationUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Recommendation:
    """A rep can only move a Recommendation's status (accepted/dismissed) -
    every other field is system-generated by the AI Analysis Engine and
    stays read-only here."""
    _get_prospect_or_404(db, profile.id, prospect_id)
    recommendation = _get_recommendation_or_404(db, prospect_id, recommendation_id)
    recommendation.status = recommendation_in.status
    db.commit()
    db.refresh(recommendation)
    return recommendation
