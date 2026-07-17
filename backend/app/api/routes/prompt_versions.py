import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.prompt_version import PromptVersion
from app.schemas.prompt_version import PromptVersionCreate, PromptVersionRead

router = APIRouter()

# AI behavior instructions - deliberately separate from OutreachPlaybook
# (business knowledge). Most prompts are expected to stay global/system
# (company_profile_id IS NULL), maintained centrally; a business only gets
# its own row if it genuinely needs different AI guardrails. Append-only:
# creating a new version never edits a previous row, and deactivates any
# prior active row for the same (company_profile_id, channel_key,
# prompt_key) lineage.


@router.get("/company-profiles/{company_profile_id}/prompt-versions", response_model=list[PromptVersionRead])
def list_prompt_versions(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[PromptVersion]:
    stmt = (
        select(PromptVersion)
        .where(or_(PromptVersion.company_profile_id == profile.id, PromptVersion.company_profile_id.is_(None)))
        .order_by(PromptVersion.channel_key, PromptVersion.prompt_key, PromptVersion.version.desc())
    )
    return list(db.scalars(stmt).all())


@router.post(
    "/company-profiles/{company_profile_id}/prompt-versions",
    response_model=PromptVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_prompt_version(
    prompt_in: PromptVersionCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> PromptVersion:
    next_version = (
        db.scalar(
            select(func.coalesce(func.max(PromptVersion.version), 0)).where(
                PromptVersion.company_profile_id == profile.id,
                PromptVersion.channel_key == prompt_in.channel_key,
                PromptVersion.prompt_key == prompt_in.prompt_key,
            )
        )
        + 1
    )
    # Deactivate any prior active row for this business's same lineage -
    # the global/system-default lineage (company_profile_id IS NULL) is
    # untouched, since a business override doesn't change what other
    # businesses use.
    previous_active = db.scalars(
        select(PromptVersion).where(
            PromptVersion.company_profile_id == profile.id,
            PromptVersion.channel_key == prompt_in.channel_key,
            PromptVersion.prompt_key == prompt_in.prompt_key,
            PromptVersion.is_active.is_(True),
        )
    ).all()
    for row in previous_active:
        row.is_active = False

    prompt_version = PromptVersion(
        company_profile_id=profile.id,
        version=next_version,
        is_active=True,
        **prompt_in.model_dump(),
    )
    db.add(prompt_version)
    db.commit()
    db.refresh(prompt_version)
    return prompt_version


@router.get("/company-profiles/{company_profile_id}/prompt-versions/{prompt_version_id}", response_model=PromptVersionRead)
def get_prompt_version(
    prompt_version_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> PromptVersion:
    prompt_version = db.get(PromptVersion, prompt_version_id)
    if prompt_version is None or (
        prompt_version.company_profile_id != profile.id and prompt_version.company_profile_id is not None
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt version not found")
    return prompt_version
