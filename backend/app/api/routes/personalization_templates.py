import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.personalization_template import PersonalizationTemplate
from app.schemas.personalization_template import (
    PersonalizationTemplateCreate,
    PersonalizationTemplateRead,
    PersonalizationTemplateUpdate,
)

router = APIRouter()

# Exact mirror of research_templates.py / search_templates.py. System-seeded
# starter templates (company_profile_id IS NULL) are visible to every
# business but never directly editable/deletable - a business clones one
# into its own row before customizing it.


@router.get("/company-profiles/{company_profile_id}/personalization-templates", response_model=list[PersonalizationTemplateRead])
def list_personalization_templates(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[PersonalizationTemplate]:
    stmt = (
        select(PersonalizationTemplate)
        .where(or_(PersonalizationTemplate.company_profile_id == profile.id, PersonalizationTemplate.is_system_default.is_(True)))
        .order_by(PersonalizationTemplate.is_system_default.desc(), PersonalizationTemplate.name)
    )
    return list(db.scalars(stmt).all())


@router.post("/company-profiles/{company_profile_id}/personalization-templates", response_model=PersonalizationTemplateRead, status_code=status.HTTP_201_CREATED)
def create_personalization_template(
    template_in: PersonalizationTemplateCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> PersonalizationTemplate:
    template = PersonalizationTemplate(company_profile_id=profile.id, is_system_default=False, **template_in.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def _get_visible_template_or_404(db: Session, profile_id: uuid.UUID, template_id: uuid.UUID) -> PersonalizationTemplate:
    template = db.get(PersonalizationTemplate, template_id)
    if template is None or (template.company_profile_id != profile_id and not template.is_system_default):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Personalization template not found")
    return template


def _get_owned_template_or_404(db: Session, profile_id: uuid.UUID, template_id: uuid.UUID) -> PersonalizationTemplate:
    template = db.get(PersonalizationTemplate, template_id)
    if template is None or template.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Personalization template not found or not editable")
    return template


@router.get("/company-profiles/{company_profile_id}/personalization-templates/{template_id}", response_model=PersonalizationTemplateRead)
def get_personalization_template(
    template_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> PersonalizationTemplate:
    return _get_visible_template_or_404(db, profile.id, template_id)


@router.post(
    "/company-profiles/{company_profile_id}/personalization-templates/{template_id}/clone",
    response_model=PersonalizationTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
def clone_personalization_template(
    template_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> PersonalizationTemplate:
    source = _get_visible_template_or_404(db, profile.id, template_id)
    clone = PersonalizationTemplate(
        company_profile_id=profile.id,
        name=f"{source.name} (copy)",
        description=source.description,
        personalization_spec=dict(source.personalization_spec or {}),
        is_system_default=False,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone


@router.put("/company-profiles/{company_profile_id}/personalization-templates/{template_id}", response_model=PersonalizationTemplateRead)
def update_personalization_template(
    template_id: uuid.UUID,
    template_in: PersonalizationTemplateUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> PersonalizationTemplate:
    template = _get_owned_template_or_404(db, profile.id, template_id)
    for field, value in template_in.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    db.commit()
    db.refresh(template)
    return template


@router.delete("/company-profiles/{company_profile_id}/personalization-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_personalization_template(
    template_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> None:
    template = _get_owned_template_or_404(db, profile.id, template_id)
    db.delete(template)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This template is used by at least one Personalization Request and can't be deleted while in use.",
        )
