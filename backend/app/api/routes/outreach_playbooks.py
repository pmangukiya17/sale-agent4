import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.outreach_block import OutreachBlock
from app.models.outreach_playbook import OutreachPlaybook
from app.schemas.outreach_playbook import (
    OutreachPlaybookCreate,
    OutreachPlaybookRead,
    OutreachPlaybookReviseRequest,
)

router = APIRouter()

# OutreachPlaybook replaces the originally-proposed OutreachTemplate.
# System-seeded starter playbooks (company_profile_id IS NULL) are visible
# to every business but never directly editable/deletable - a business
# clones one into its own row before customizing it, same convention as
# every *Template model. Unlike a Template, a playbook is VERSIONED - see
# /revise below for how a new version is created without ever editing a
# previous one in place.


def _blocks_options():
    return (selectinload(OutreachPlaybook.blocks),)


@router.get("/company-profiles/{company_profile_id}/outreach-playbooks", response_model=list[OutreachPlaybookRead])
def list_outreach_playbooks(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[OutreachPlaybook]:
    # Only current versions are listed - older versions stay reachable via
    # get_outreach_playbook(id) for audit/comparison, not in the main list.
    stmt = (
        select(OutreachPlaybook)
        .where(
            or_(OutreachPlaybook.company_profile_id == profile.id, OutreachPlaybook.is_system_default.is_(True)),
            OutreachPlaybook.is_current.is_(True),
        )
        .options(*_blocks_options())
        .order_by(OutreachPlaybook.is_system_default.desc(), OutreachPlaybook.name)
    )
    return list(db.scalars(stmt).all())


@router.post(
    "/company-profiles/{company_profile_id}/outreach-playbooks",
    response_model=OutreachPlaybookRead,
    status_code=status.HTTP_201_CREATED,
)
def create_outreach_playbook(
    playbook_in: OutreachPlaybookCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> OutreachPlaybook:
    data = playbook_in.model_dump(exclude={"blocks"})
    playbook = OutreachPlaybook(
        company_profile_id=profile.id,
        version=1,
        is_current=True,
        derived_from_playbook_version=None,
        is_system_default=False,
        **data,
    )
    db.add(playbook)
    db.flush()
    for block_in in playbook_in.blocks:
        db.add(OutreachBlock(outreach_playbook_id=playbook.id, **block_in.model_dump()))
    db.commit()
    db.refresh(playbook)
    return playbook


def _get_visible_playbook_or_404(db: Session, profile_id: uuid.UUID, playbook_id: uuid.UUID) -> OutreachPlaybook:
    stmt = select(OutreachPlaybook).where(OutreachPlaybook.id == playbook_id).options(*_blocks_options())
    playbook = db.scalars(stmt).first()
    if playbook is None or (playbook.company_profile_id != profile_id and not playbook.is_system_default):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outreach playbook not found")
    return playbook


def _get_owned_playbook_or_404(db: Session, profile_id: uuid.UUID, playbook_id: uuid.UUID) -> OutreachPlaybook:
    playbook = db.get(OutreachPlaybook, playbook_id)
    if playbook is None or playbook.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outreach playbook not found or not editable")
    return playbook


@router.get("/company-profiles/{company_profile_id}/outreach-playbooks/{playbook_id}", response_model=OutreachPlaybookRead)
def get_outreach_playbook(
    playbook_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> OutreachPlaybook:
    return _get_visible_playbook_or_404(db, profile.id, playbook_id)


@router.post(
    "/company-profiles/{company_profile_id}/outreach-playbooks/{playbook_id}/clone",
    response_model=OutreachPlaybookRead,
    status_code=status.HTTP_201_CREATED,
)
def clone_outreach_playbook(
    playbook_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> OutreachPlaybook:
    source = _get_visible_playbook_or_404(db, profile.id, playbook_id)
    clone = OutreachPlaybook(
        company_profile_id=profile.id,
        name=f"{source.name} (copy)",
        description=source.description,
        playbook_goal=source.playbook_goal,
        version=1,
        is_current=True,
        derived_from_playbook_version=None,
        is_system_default=False,
        sales_methodology=source.sales_methodology,
        brand_voice=source.brand_voice,
        core_value_proposition=source.core_value_proposition,
        communication_principles=list(source.communication_principles or []),
        personalization_rules=dict(source.personalization_rules or {}),
        channel_preferences=dict(source.channel_preferences or {}),
        cta_strategy=source.cta_strategy,
    )
    db.add(clone)
    db.flush()
    for block in source.blocks:
        db.add(
            OutreachBlock(
                outreach_playbook_id=clone.id,
                block_key=block.block_key,
                behavior=block.behavior,
                fixed_content=block.fixed_content,
                ai_guidance=block.ai_guidance,
                applicable_channels=list(block.applicable_channels) if block.applicable_channels else None,
                is_mandatory=block.is_mandatory,
                display_order=block.display_order,
            )
        )
    db.commit()
    db.refresh(clone)
    return clone


@router.post(
    "/company-profiles/{company_profile_id}/outreach-playbooks/{playbook_id}/revise",
    response_model=OutreachPlaybookRead,
    status_code=status.HTTP_201_CREATED,
)
def revise_outreach_playbook(
    playbook_id: uuid.UUID,
    revision_in: OutreachPlaybookReviseRequest,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> OutreachPlaybook:
    """
    Creates version N+1 of an existing playbook lineage - never edits the
    previous version's row. The previous is_current row is flipped to
    False; derived_from_playbook_version records exactly which version
    this one was revised from, per the explicit ancestry requirement.
    """
    previous = _get_owned_playbook_or_404(db, profile.id, playbook_id)
    next_version = (
        db.scalar(
            select(func.coalesce(func.max(OutreachPlaybook.version), 0)).where(
                OutreachPlaybook.company_profile_id == profile.id, OutreachPlaybook.name == previous.name
            )
        )
        + 1
    )
    previous.is_current = False

    data = revision_in.model_dump(exclude={"blocks"})
    revised = OutreachPlaybook(
        company_profile_id=profile.id,
        version=next_version,
        is_current=True,
        derived_from_playbook_version=previous.version,
        is_system_default=False,
        **data,
    )
    db.add(revised)
    db.flush()
    for block_in in revision_in.blocks:
        db.add(OutreachBlock(outreach_playbook_id=revised.id, **block_in.model_dump()))
    db.commit()
    db.refresh(revised)
    return revised


@router.delete("/company-profiles/{company_profile_id}/outreach-playbooks/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_outreach_playbook(
    playbook_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> None:
    playbook = _get_owned_playbook_or_404(db, profile.id, playbook_id)
    db.delete(playbook)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This playbook version is used by at least one Outreach Request/Draft and can't be deleted while in use.",
        )
