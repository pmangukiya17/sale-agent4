import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.buyer_type import BuyerType
from app.models.company_profile import CompanyProfile
from app.models.country import Country
from app.models.icp_criteria import ICPCriteria
from app.models.language import Language
from app.schemas.icp_criteria import ICPCriteriaCreate, ICPCriteriaRead, ICPCriteriaUpdate

router = APIRouter()


def _resolve_ids(db: Session, model, ids: list[uuid.UUID], label: str) -> list:
    if not ids:
        return []
    rows = db.scalars(select(model).where(model.id.in_(ids))).all()
    missing = set(ids) - {row.id for row in rows}
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown {label} id(s): {missing}")
    return list(rows)


def _apply_relations(db: Session, icp: ICPCriteria, data: ICPCriteriaCreate | ICPCriteriaUpdate) -> None:
    if data.target_buyer_type_ids is not None:
        icp.target_buyer_types = _resolve_ids(db, BuyerType, data.target_buyer_type_ids, "buyer type")
    if data.target_market_country_ids is not None:
        icp.target_markets = _resolve_ids(db, Country, data.target_market_country_ids, "country")
    if data.excluded_country_ids is not None:
        icp.excluded_countries = _resolve_ids(db, Country, data.excluded_country_ids, "country")
    if data.language_ids is not None:
        icp.languages = _resolve_ids(db, Language, data.language_ids, "language")


@router.get("/company-profiles/{company_profile_id}/icp-criteria", response_model=list[ICPCriteriaRead])
def list_icp_criteria(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[ICPCriteria]:
    stmt = (
        select(ICPCriteria)
        .where(ICPCriteria.company_profile_id == profile.id)
        .order_by(ICPCriteria.version.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("/company-profiles/{company_profile_id}/icp-criteria", response_model=ICPCriteriaRead, status_code=status.HTTP_201_CREATED)
def create_icp_criteria(
    icp_in: ICPCriteriaCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ICPCriteria:
    # Auto-assign the next version for this company rather than trusting the
    # client to track it - this is what makes ICPCriteria a version history
    # instead of just another editable row.
    next_version = (
        db.scalar(
            select(func.coalesce(func.max(ICPCriteria.version), 0)).where(
                ICPCriteria.company_profile_id == profile.id
            )
        )
        + 1
    )

    data = icp_in.model_dump(
        exclude={"target_buyer_type_ids", "target_market_country_ids", "excluded_country_ids", "language_ids"}
    )
    icp = ICPCriteria(company_profile_id=profile.id, version=next_version, **data)
    db.add(icp)
    db.flush()
    _apply_relations(db, icp, icp_in)
    db.commit()
    db.refresh(icp)
    return icp


def _get_icp_or_404(db: Session, profile_id: uuid.UUID, icp_id: uuid.UUID) -> ICPCriteria:
    icp = db.get(ICPCriteria, icp_id)
    if icp is None or icp.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ICP criteria not found")
    return icp


@router.get("/company-profiles/{company_profile_id}/icp-criteria/{icp_id}", response_model=ICPCriteriaRead)
def get_icp_criteria(
    icp_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ICPCriteria:
    return _get_icp_or_404(db, profile.id, icp_id)


@router.put("/company-profiles/{company_profile_id}/icp-criteria/{icp_id}", response_model=ICPCriteriaRead)
def update_icp_criteria(
    icp_id: uuid.UUID,
    icp_in: ICPCriteriaUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ICPCriteria:
    icp = _get_icp_or_404(db, profile.id, icp_id)
    data = icp_in.model_dump(
        exclude={"target_buyer_type_ids", "target_market_country_ids", "excluded_country_ids", "language_ids"},
        exclude_unset=True,
    )
    for field, value in data.items():
        setattr(icp, field, value)
    _apply_relations(db, icp, icp_in)
    db.commit()
    db.refresh(icp)
    return icp


@router.delete("/company-profiles/{company_profile_id}/icp-criteria/{icp_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_icp_criteria(
    icp_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> None:
    icp = _get_icp_or_404(db, profile.id, icp_id)
    db.delete(icp)
    db.commit()
