import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate

router = APIRouter()


@router.get("/company-profiles/{company_profile_id}/products", response_model=list[ProductRead])
def list_products(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[Product]:
    stmt = select(Product).where(Product.company_profile_id == profile.id).order_by(Product.created_at.desc())
    return list(db.scalars(stmt).all())


@router.post("/company-profiles/{company_profile_id}/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    product_in: ProductCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Product:
    product = Product(company_profile_id=profile.id, **product_in.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def _get_product_or_404(db: Session, profile_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    product = db.get(Product, product_id)
    if product is None or product.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.get("/company-profiles/{company_profile_id}/products/{product_id}", response_model=ProductRead)
def get_product(
    product_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Product:
    return _get_product_or_404(db, profile.id, product_id)


@router.put("/company-profiles/{company_profile_id}/products/{product_id}", response_model=ProductRead)
def update_product(
    product_id: uuid.UUID,
    product_in: ProductUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Product:
    product = _get_product_or_404(db, profile.id, product_id)
    for field, value in product_in.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/company-profiles/{company_profile_id}/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> None:
    product = _get_product_or_404(db, profile.id, product_id)
    db.delete(product)
    db.commit()
