from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.buyer_type import BuyerType
from app.models.country import Country
from app.models.currency import Currency
from app.models.industry import Industry
from app.models.language import Language
from app.models.user import User
from app.schemas.reference import BuyerTypeRead, CountryRead, CurrencyRead, IndustryRead, LanguageRead

router = APIRouter()

# Read-only lookups that populate the multi-select inputs on the Company
# Profile / ICP forms. All backed by real tables (see migration 0002), not
# hardcoded lists, so adding a new option is a data change, not a code
# deploy.


@router.get("/buyer-types", response_model=list[BuyerTypeRead])
def list_buyer_types(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[BuyerType]:
    stmt = select(BuyerType).where(BuyerType.is_active.is_(True)).order_by(BuyerType.name)
    return list(db.scalars(stmt).all())


@router.get("/industries", response_model=list[IndustryRead])
def list_industries(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[Industry]:
    stmt = select(Industry).where(Industry.is_active.is_(True)).order_by(Industry.name)
    return list(db.scalars(stmt).all())


@router.get("/countries", response_model=list[CountryRead])
def list_countries(
    region: str | None = Query(None, description="Filter to a region, e.g. 'Europe'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Country]:
    stmt = select(Country).where(Country.is_active.is_(True))
    if region:
        stmt = stmt.where(Country.region == region)
    stmt = stmt.order_by(Country.name)
    return list(db.scalars(stmt).all())


@router.get("/languages", response_model=list[LanguageRead])
def list_languages(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[Language]:
    stmt = select(Language).where(Language.is_active.is_(True)).order_by(Language.name)
    return list(db.scalars(stmt).all())


@router.get("/currencies", response_model=list[CurrencyRead])
def list_currencies(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[Currency]:
    stmt = select(Currency).where(Currency.is_active.is_(True)).order_by(Currency.name)
    return list(db.scalars(stmt).all())
