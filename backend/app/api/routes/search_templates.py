import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.search_template import SearchTemplate
from app.schemas.search_template import SearchTemplateCreate, SearchTemplateRead, SearchTemplateUpdate

router = APIRouter()

# System-seeded starter templates (company_profile_id IS NULL) are visible
# to every business but never directly editable/deletable - a business
# clones one into its own row (POST .../clone) before customizing it, the
# same "seed, then clone/override" pattern used for reference data.


@router.get("/company-profiles/{company_profile_id}/search-templates", response_model=list[SearchTemplateRead])
def list_search_templates(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[SearchTemplate]:
    stmt = (
        select(SearchTemplate)
        .where(or_(SearchTemplate.company_profile_id == profile.id, SearchTemplate.is_system_default.is_(True)))
        .order_by(SearchTemplate.is_system_default.desc(), SearchTemplate.name)
    )
    return list(db.scalars(stmt).all())


@router.post("/company-profiles/{company_profile_id}/search-templates", response_model=SearchTemplateRead, status_code=status.HTTP_201_CREATED)
def create_search_template(
    template_in: SearchTemplateCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> SearchTemplate:
    template = SearchTemplate(company_profile_id=profile.id, is_system_default=False, **template_in.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def _get_visible_template_or_404(db: Session, profile_id: uuid.UUID, template_id: uuid.UUID) -> SearchTemplate:
    template = db.get(SearchTemplate, template_id)
    if template is None or (template.company_profile_id != profile_id and not template.is_system_default):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search template not found")
    return template


def _get_owned_template_or_404(db: Session, profile_id: uuid.UUID, template_id: uuid.UUID) -> SearchTemplate:
    template = db.get(SearchTemplate, template_id)
    if template is None or template.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search template not found or not editable")
    return template


@router.get("/company-profiles/{company_profile_id}/search-templates/{template_id}", response_model=SearchTemplateRead)
def get_search_template(
    template_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> SearchTemplate:
    return _get_visible_template_or_404(db, profile.id, template_id)


@router.post(
    "/company-profiles/{company_profile_id}/search-templates/{template_id}/clone",
    response_model=SearchTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
def clone_search_template(
    template_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> SearchTemplate:
    source = _get_visible_template_or_404(db, profile.id, template_id)
    clone = SearchTemplate(
        company_profile_id=profile.id,
        name=f"{source.name} (copy)",
        description=source.description,
        query_spec=dict(source.query_spec or {}),
        is_system_default=False,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone


@router.put("/company-profiles/{company_profile_id}/search-templates/{template_id}", response_model=SearchTemplateRead)
def update_search_template(
    template_id: uuid.UUID,
    template_in: SearchTemplateUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> SearchTemplate:
    template = _get_owned_template_or_404(db, profile.id, template_id)
    for field, value in template_in.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    db.commit()
    db.refresh(template)
    return template


@router.delete("/company-profiles/{company_profile_id}/search-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_search_template(
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
            detail="This template is used by at least one Discovery Search and can't be deleted while in use.",
        )
