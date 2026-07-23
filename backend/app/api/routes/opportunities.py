import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.enums import OpportunityStage
from app.models.opportunity import Opportunity
from app.models.prospect import Prospect
from app.models.user import User
from app.opportunities.service import advance_stage, compute_funnel, compute_pipeline_value, create_opportunity
from app.opportunities.state_machine import InvalidStageTransitionError
from app.schemas.opportunity import (
    AdvanceStageRequest,
    OpportunityCreate,
    OpportunityCurrencyPipelineValue,
    OpportunityFunnelStage,
    OpportunityRead,
    OpportunityUpdate,
)

router = APIRouter()

# Track C3 (dashboard-capabilities-architecture-plan.md, Section 1). Every
# route below goes through get_owned_company_profile, the same dependency
# prospects.py/prospect_contacts.py/conversations.py already use - no new
# isolation mechanism invented; Opportunity is a first-class M8-era table
# from birth, never adjacent to the legacy Company/Contact.
#
# Route ordering matters here exactly as it did for Track C1's
# .../conversations/count: /opportunities/funnel and
# /opportunities/pipeline-value are both static path segments that must be
# registered BEFORE the dynamic /opportunities/{opportunity_id} route, or
# FastAPI/Starlette would hand "funnel"/"pipeline-value" to the dynamic
# route's uuid.UUID parser first and 422. verify_track_c3.sh asserts this
# ordering directly against the real running app, same as
# verify_track_c1.sh already does for conversations.


def _get_prospect_or_404(db: Session, profile_id: uuid.UUID, prospect_id: uuid.UUID) -> Prospect:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None or prospect.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return prospect


def _get_opportunity_or_404(db: Session, profile_id: uuid.UUID, opportunity_id: uuid.UUID) -> Opportunity:
    opportunity = db.get(Opportunity, opportunity_id)
    if opportunity is None or opportunity.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    return opportunity


@router.post(
    "/company-profiles/{company_profile_id}/opportunities",
    response_model=OpportunityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_opportunity_route(
    opportunity_in: OpportunityCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Opportunity:
    _get_prospect_or_404(db, profile.id, opportunity_in.prospect_id)
    data = opportunity_in.model_dump()
    stage = data.pop("stage")
    prospect_id = data.pop("prospect_id")
    name = data.pop("name")
    return create_opportunity(
        db,
        company_profile_id=profile.id,
        prospect_id=prospect_id,
        name=name,
        stage=stage,
        **data,
    )


@router.get(
    "/company-profiles/{company_profile_id}/opportunities",
    response_model=list[OpportunityRead],
)
def list_opportunities(
    stage: OpportunityStage | None = Query(None),
    prospect_id: uuid.UUID | None = Query(None),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[Opportunity]:
    stmt = select(Opportunity).where(Opportunity.company_profile_id == profile.id)
    if stage is not None:
        stmt = stmt.where(Opportunity.stage == stage)
    if prospect_id is not None:
        stmt = stmt.where(Opportunity.prospect_id == prospect_id)
    stmt = stmt.order_by(Opportunity.created_at.desc())
    return list(db.scalars(stmt).all())


@router.get(
    "/company-profiles/{company_profile_id}/opportunities/funnel",
    response_model=list[OpportunityFunnelStage],
)
def get_opportunity_funnel(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[dict]:
    return compute_funnel(db, profile.id)


@router.get(
    "/company-profiles/{company_profile_id}/opportunities/pipeline-value",
    response_model=list[OpportunityCurrencyPipelineValue],
)
def get_opportunity_pipeline_value(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Returns one row per distinct currency in use (Track C4 fix -
    resolves Section 4.10's deferred currency-mixing decision) - see
    compute_pipeline_value's own docstring. An empty list means this
    business has no Opportunities at all yet."""
    return compute_pipeline_value(db, profile.id)


@router.get(
    "/company-profiles/{company_profile_id}/opportunities/{opportunity_id}",
    response_model=OpportunityRead,
)
def get_opportunity(
    opportunity_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Opportunity:
    return _get_opportunity_or_404(db, profile.id, opportunity_id)


@router.patch(
    "/company-profiles/{company_profile_id}/opportunities/{opportunity_id}",
    response_model=OpportunityRead,
)
def update_opportunity(
    opportunity_id: uuid.UUID,
    opportunity_in: OpportunityUpdate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Opportunity:
    """Never accepts `stage` - see OpportunityUpdate's own docstring. A
    stage change always goes through advance-stage below so every
    transition is guaranteed an OpportunityStageHistory row."""
    opportunity = _get_opportunity_or_404(db, profile.id, opportunity_id)
    for field, value in opportunity_in.model_dump(exclude_unset=True).items():
        setattr(opportunity, field, value)
    db.commit()
    db.refresh(opportunity)
    return opportunity


@router.post(
    "/company-profiles/{company_profile_id}/opportunities/{opportunity_id}/advance-stage",
    response_model=OpportunityRead,
)
def advance_opportunity_stage(
    opportunity_id: uuid.UUID,
    request: AdvanceStageRequest,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Opportunity:
    """The only endpoint that ever changes Opportunity.stage. Per the
    CEO's explicit direction, ANY (from, to) stage pair is accepted -
    skipping stages, or moving "backwards" (e.g. re-opening a
    CLOSED_LOST deal), is never rejected as a workflow-order violation.
    The only rejected case is a same-stage no-op (state_machine.
    InvalidStageTransitionError), translated to a 400 here."""
    opportunity = _get_opportunity_or_404(db, profile.id, opportunity_id)
    try:
        return advance_stage(
            db,
            opportunity,
            request.to_stage,
            changed_by_user_id=current_user.id,
            lost_reason=request.lost_reason,
        )
    except InvalidStageTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete(
    "/company-profiles/{company_profile_id}/opportunities/{opportunity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_opportunity(
    opportunity_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> None:
    """Hard delete only remains available for an Opportunity that has
    never actually progressed beyond its own creation - i.e. exactly one
    OpportunityStageHistory row (the automatic from_stage=None entry
    every create_opportunity call writes). The moment a real stage
    transition has been recorded, this is genuine execution history
    under this project's platform-wide lifecycle rule
    (deferred-items-and-design-boundaries.md) and hard delete is
    refused - the same "archive over destroy" philosophy already applied
    to Prospect/ProspectContact/DiscoverySearch, interpreted here for a
    domain that (deliberately, in this initial slice - see the
    architecture doc's Section 9 non-goals) has no separate archive
    lifecycle of its own yet: moving a deal to CLOSED_LOST is the
    functional equivalent of "putting it to rest" without deleting the
    row or its history."""
    opportunity = _get_opportunity_or_404(db, profile.id, opportunity_id)
    if len(opportunity.stage_history) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This opportunity has recorded stage history and can't be hard-deleted. "
            "Move it to closed_lost instead to retire it while preserving its history.",
        )
    db.delete(opportunity)
    db.commit()
