"""
DeliveryCampaign lifecycle routes - create (freezes N approved
OutreachDrafts into DeliveryQueueItems), schedule, pause, resume, cancel.
See campaign_service.py for the actual logic; these routes are a thin
HTTP wrapper that maps CampaignServiceError to 400, same pattern
OutreachConfigError/ResearchConfigError already use in M2/M4.

Deliberately does not expose a raw create-then-separately-add-drafts flow
- outreach_draft_ids is supplied once, at creation, matching
campaign_service.create_campaign's all-or-nothing semantics (see its
docstring: a bad id in the list fails the whole create, no partial
campaign left behind).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.delivery.campaign_service import (
    ACTIVELY_QUEUED_STATUSES,
    CampaignServiceError,
    cancel_campaign,
    create_campaign,
    pause_campaign,
    resume_campaign,
    schedule_campaign,
)
from app.models.company_profile import CompanyProfile
from app.models.delivery_campaign import DeliveryCampaign
from app.models.delivery_queue_item import DeliveryQueueItem
from app.models.enums import OutreachDraftStatus
from app.models.outreach_draft import OutreachDraft
from app.models.prospect_contact import ProspectContact
from app.models.user import User
from app.schemas.delivery_campaign import (
    AvailableOutreachDraftRead,
    DeliveryCampaignActionBody,
    DeliveryCampaignCancelBody,
    DeliveryCampaignCreate,
    DeliveryCampaignRead,
)

router = APIRouter()


@router.get("/company-profiles/{company_profile_id}/delivery-campaigns", response_model=list[DeliveryCampaignRead])
def list_delivery_campaigns(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[DeliveryCampaign]:
    stmt = (
        select(DeliveryCampaign)
        .where(DeliveryCampaign.company_profile_id == profile.id)
        .order_by(DeliveryCampaign.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post(
    "/company-profiles/{company_profile_id}/delivery-campaigns",
    response_model=DeliveryCampaignRead,
    status_code=status.HTTP_201_CREATED,
)
def create_delivery_campaign(
    campaign_in: DeliveryCampaignCreate,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeliveryCampaign:
    """
    Created in DRAFT status with all queue items QUEUED but unscheduled -
    a separate call to POST .../schedule assigns actual send times. Kept
    as two steps (not one) so a campaign can be reviewed - "does this
    look right" - before the scheduler commits to real send times.
    """
    try:
        return create_campaign(
            db,
            company_profile_id=profile.id,
            created_by_user_id=current_user.id,
            **campaign_in.model_dump(),
        )
    except CampaignServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# Registered BEFORE the {campaign_id} routes below on purpose - "available-
# drafts" is a literal path segment at the same depth as {campaign_id},
# and FastAPI/Starlette matches routes in registration order (see
# provider_connections.py's docstring for the full explanation of this
# exact bug class - a {campaign_id} route registered first would swallow
# this one, since Starlette matches the path shape before FastAPI tries -
# and fails - to parse "available-drafts" as a UUID).
@router.get(
    "/company-profiles/{company_profile_id}/delivery-campaigns/available-drafts",
    response_model=list[AvailableOutreachDraftRead],
)
def list_available_outreach_drafts(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[AvailableOutreachDraftRead]:
    """Business-wide picker source for campaign creation - every APPROVED,
    is_current OutreachDraft for this business that does NOT already have
    an active DeliveryQueueItem (see campaign_service.ACTIVELY_QUEUED_STATUSES,
    the single shared definition this and _enqueue_draft's own pre-insert
    guard both use). Deliberately excludes drafts that are already queued
    elsewhere rather than letting the frontend offer one and have
    create_campaign reject it with a 400 - the whole point of this
    endpoint is to make the picker only ever show what's genuinely
    available right now."""
    actively_queued_subq = select(DeliveryQueueItem.outreach_draft_id).where(
        DeliveryQueueItem.status.in_(ACTIVELY_QUEUED_STATUSES)
    )
    stmt = (
        select(OutreachDraft)
        .where(
            OutreachDraft.company_profile_id == profile.id,
            OutreachDraft.status == OutreachDraftStatus.APPROVED,
            OutreachDraft.is_current.is_(True),
            OutreachDraft.id.notin_(actively_queued_subq),
        )
        .options(selectinload(OutreachDraft.prospect_contact).selectinload(ProspectContact.prospect))
        .order_by(OutreachDraft.created_at.desc())
    )
    drafts = db.scalars(stmt).all()

    result: list[AvailableOutreachDraftRead] = []
    for draft in drafts:
        contact = draft.prospect_contact
        prospect = contact.prospect if contact else None
        assembled = (draft.current_content or {}).get("assembled", {})
        result.append(
            AvailableOutreachDraftRead(
                id=draft.id,
                channel_key=draft.channel_key,
                version=draft.version,
                confidence=draft.confidence,
                prospect_id=draft.prospect_id,
                prospect_name=prospect.name if prospect else "Unknown prospect",
                prospect_contact_id=draft.prospect_contact_id,
                contact_name=contact.name if contact else None,
                contact_email=contact.email if contact else None,
                subject_preview=assembled.get("subject"),
            )
        )
    return result


def _get_campaign_or_404(db: Session, profile_id: uuid.UUID, campaign_id: uuid.UUID) -> DeliveryCampaign:
    campaign = db.get(DeliveryCampaign, campaign_id)
    if campaign is None or campaign.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery campaign not found")
    return campaign


@router.get("/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}", response_model=DeliveryCampaignRead)
def get_delivery_campaign(
    campaign_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> DeliveryCampaign:
    return _get_campaign_or_404(db, profile.id, campaign_id)


@router.post(
    "/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}/schedule",
    response_model=DeliveryCampaignRead,
)
def schedule_delivery_campaign(
    campaign_id: uuid.UUID,
    _body: DeliveryCampaignActionBody | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> DeliveryCampaign:
    _get_campaign_or_404(db, profile.id, campaign_id)
    try:
        return schedule_campaign(db, campaign_id)
    except CampaignServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}/pause",
    response_model=DeliveryCampaignRead,
)
def pause_delivery_campaign(
    campaign_id: uuid.UUID,
    _body: DeliveryCampaignActionBody | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> DeliveryCampaign:
    _get_campaign_or_404(db, profile.id, campaign_id)
    try:
        return pause_campaign(db, campaign_id)
    except CampaignServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}/resume",
    response_model=DeliveryCampaignRead,
)
def resume_delivery_campaign(
    campaign_id: uuid.UUID,
    _body: DeliveryCampaignActionBody | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> DeliveryCampaign:
    _get_campaign_or_404(db, profile.id, campaign_id)
    try:
        return resume_campaign(db, campaign_id)
    except CampaignServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}/cancel",
    response_model=DeliveryCampaignRead,
)
def cancel_delivery_campaign(
    campaign_id: uuid.UUID,
    _body: DeliveryCampaignCancelBody | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> DeliveryCampaign:
    """_body.reason is accepted for forward-compat (see
    DeliveryCampaignCancelBody's docstring) but not yet plumbed into
    cancel_campaign, which always logs "campaign_cancelled" today -
    threading a custom reason through is a small, additive follow-up, not
    a redesign."""
    _get_campaign_or_404(db, profile.id, campaign_id)
    try:
        return cancel_campaign(db, campaign_id)
    except CampaignServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
