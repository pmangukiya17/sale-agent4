"""
Business Branding routes, deliberately namespaced under /branding/... rather
than nested purely under /company-profiles/{id}/... - this keeps Branding
its own domain in the API surface (mirroring how it's its own module in the
architecture) rather than appearing to be just another CompanyProfile field.
get_owned_company_profile resolves company_profile_id by parameter name
regardless of where it sits in the path, so this namespace choice required
no dependency changes.

Follows the same "auto-bootstrap on first GET, mutate in place via PUT"
convention as workspace_settings.py - there is always exactly zero or one
signature row per business, never created explicitly by the client.
"""
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.api.deps import get_owned_company_profile
from app.branding.plain_text import html_to_plain_text
from app.db.session import get_db
from app.models.brand_email_signature import BrandEmailSignature
from app.models.company_profile import CompanyProfile
from app.schemas.brand_email_signature import BrandEmailSignatureRead, BrandEmailSignatureUpdate

router = APIRouter()


def _get_or_create(db: Session, profile: CompanyProfile) -> BrandEmailSignature:
    signature = (
        db.query(BrandEmailSignature)
        .filter(BrandEmailSignature.company_profile_id == profile.id)
        .first()
    )
    if signature is None:
        signature = BrandEmailSignature(company_profile_id=profile.id)
        db.add(signature)
        db.commit()
        db.refresh(signature)
    return signature


@router.get("/branding/company-profiles/{company_profile_id}/email-signature", response_model=BrandEmailSignatureRead)
def get_email_signature(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> BrandEmailSignature:
    return _get_or_create(db, profile)


@router.put("/branding/company-profiles/{company_profile_id}/email-signature", response_model=BrandEmailSignatureRead)
def update_email_signature(
    signature_in: BrandEmailSignatureUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> BrandEmailSignature:
    signature = _get_or_create(db, profile)

    signature.signature_html = signature_in.signature_html
    signature.signature_plain_text = html_to_plain_text(signature_in.signature_html)
    signature.is_active = signature_in.is_active

    db.commit()
    db.refresh(signature)
    return signature
