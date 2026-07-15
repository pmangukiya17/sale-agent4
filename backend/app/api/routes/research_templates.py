import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.research_template import ResearchTemplate
from app.schemas.research_template import ResearchTemplateCreate, ResearchTemplateRead, ResearchTemplateUpdate

router = APIRouter()

# Exact mirror of search_templates.py (M1). System-seeded starter templates
# (company_profile_id IS NULL) are visible to every business but never
# directly editable/deletable - a business clones one into its own row
# before customizing it.


@router.get("/company-profiles/{company_profile_id}/research-templates", response_model=list[ResearchTemplateRead])
def list_research_templates(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[ResearchTemplate]:
    stmt = (
        select(ResearchTemplate)
        .where(or_(ResearchTemplate.company_profile_id == profile.id, ResearchTemplate.is_system_default.is_(True)))
        .order_by(ResearchTemplate.is_system_default.desc(), ResearchTemplate.name)
    )
    return list(db.scalars(stmt).all())


@router.post("/company-profiles/{company_profile_id}/research-templates", response_model=ResearchTemplateRead, status_code=status.HTTP_201_CREATED)
def create_research_template(
    template_in: ResearchTemplateCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ResearchTemplate:
    template = ResearchTemplate(company_profile_id=profile.id, is_system_default=False, **template_in.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def _get_visible_template_or_404(db: Session, profile_id: uuid.UUID, template_id: uuid.UUID) -> ResearchTemplate:
    template = db.get(ResearchTemplate, template_id)
    if template is None or (template.company_profile_id != profile_id and not template.is_system_default):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research template not found")
    return template


def _get_owned_template_or_404(db: Session, profile_id: uuid.UUID, template_id: uuid.UUID) -> ResearchTemplate:
    template = db.get(ResearchTemplate, template_id)
    if template is None or template.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research template not found or not editable")
    return template


@router.get("/company-profiles/{company_profile_id}/research-templates/{template_id}", response_model=ResearchTemplateRead)
def get_research_template(
    template_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ResearchTemplate:
    return _get_visible_template_or_404(db, profile.id, template_id)


@router.post(
    "/company-profiles/{company_profile_id}/research-templates/{template_id}/clone",
    response_model=ResearchTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
def clone_research_template(
    template_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ResearchTemplate:
    source = _get_visible_template_or_404(db, profile.id, template_id)
    clone = ResearchTemplate(
        company_profile_id=profile.id,
        name=f"{source.name} (copy)",
        description=source.description,
        research_spec=dict(source.research_spec or {}),
        is_system_default=False,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone


@router.put("/company-profiles/{company_profile_id}/research-templates/{template_id}", response_model=ResearchTemplateRead)
def update_research_template(
    template_id: uuid.UUID,
    template_in: ResearchTemplateUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ResearchTemplate:
    template = _get_owned_template_or_404(db, profile.id, template_id)
    for field, value in template_in.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    db.commit()
    db.refresh(template)
    return template


@router.delete("/company-profiles/{company_profile_id}/research-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_research_template(
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
            detail="This template is used by at least one Research Request and can't be deleted while in use.",
        )
