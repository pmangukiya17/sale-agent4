import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.company import Company
from app.models.user import User
from app.schemas.company import CompanyCreate, CompanyRead

router = APIRouter()

# NOTE: This was deliberately minimal for M0 - it exists only to prove the
# CRM schema and the dashboard's read/write path end-to-end. Discovery,
# scoring, and enrichment were never implemented here; that's what
# Prospect (app/api/routes/prospects.py) actually became starting M1.
#
# DEPRECATED - Phase 1 (see Company's own model docstring and
# deferred-items-and-design-boundaries.md's legacy CRM entry). Routes kept
# working exactly as-is - nothing here is removed or behavior-changed -
# but marked deprecated=True (shows up in OpenAPI/Swagger) so new
# development doesn't get built against this model. Do not add fields,
# filters, or endpoints here; extend Prospect/ProspectContact instead.


@router.get("/companies", response_model=list[CompanyRead], deprecated=True)
def list_companies(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Company]:
    stmt = select(Company).order_by(Company.created_at.desc()).offset(skip).limit(limit)
    return list(db.scalars(stmt).all())


@router.post("/companies", response_model=CompanyRead, status_code=status.HTTP_201_CREATED, deprecated=True)
def create_company(
    company_in: CompanyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Company:
    company = Company(**company_in.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.get("/companies/{company_id}", response_model=CompanyRead, deprecated=True)
def get_company(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company
