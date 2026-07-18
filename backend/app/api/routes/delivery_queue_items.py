"""
DeliveryQueueItem read + the two human-triggered single-item actions
(Cancel, Retry Now) - see queue_service.py. Deliberately no create/update
route: queue items are only ever produced by campaign_service.create_campaign
(one per approved OutreachDraft) and only ever mutated by
campaign_service/dispatch_service/queue_service, never directly via a
generic PUT - there is no field on a queue item a client should be able
to set arbitrarily (frozen_content in particular must stay exactly what
was approved).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.delivery.queue_service import QueueServiceError, cancel_queue_item, retry_now
from app.models.company_profile import CompanyProfile
from app.models.delivery_campaign import DeliveryCampaign
from app.models.delivery_queue_item import DeliveryQueueItem
from app.schemas.delivery_queue_item import DeliveryQueueItemCancelBody, DeliveryQueueItemRead, DeliveryQueueItemRetryBody

router = APIRouter()


def _get_campaign_or_404(db: Session, profile_id: uuid.UUID, campaign_id: uuid.UUID) -> DeliveryCampaign:
    campaign = db.get(DeliveryCampaign, campaign_id)
    if campaign is None or campaign.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery campaign not found")
    return campaign


@router.get(
    "/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}/queue-items",
    response_model=list[DeliveryQueueItemRead],
)
def list_delivery_queue_items(
    campaign_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[DeliveryQueueItem]:
    _get_campaign_or_404(db, profile.id, campaign_id)
    stmt = (
        select(DeliveryQueueItem)
        .where(DeliveryQueueItem.delivery_campaign_id == campaign_id)
        .options(selectinload(DeliveryQueueItem.events))
        .order_by(DeliveryQueueItem.created_at.asc())
    )
    return list(db.scalars(stmt).all())


def _get_queue_item_or_404(db: Session, campaign_id: uuid.UUID, item_id: uuid.UUID) -> DeliveryQueueItem:
    stmt = select(DeliveryQueueItem).where(DeliveryQueueItem.id == item_id).options(selectinload(DeliveryQueueItem.events))
    item = db.scalars(stmt).first()
    if item is None or item.delivery_campaign_id != campaign_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery queue item not found")
    return item


@router.get(
    "/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}/queue-items/{item_id}",
    response_model=DeliveryQueueItemRead,
)
def get_delivery_queue_item(
    campaign_id: uuid.UUID,
    item_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> DeliveryQueueItem:
    _get_campaign_or_404(db, profile.id, campaign_id)
    return _get_queue_item_or_404(db, campaign_id, item_id)


@router.post(
    "/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}/queue-items/{item_id}/cancel",
    response_model=DeliveryQueueItemRead,
)
def cancel_delivery_queue_item(
    campaign_id: uuid.UUID,
    item_id: uuid.UUID,
    body: DeliveryQueueItemCancelBody | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> DeliveryQueueItem:
    _get_campaign_or_404(db, profile.id, campaign_id)
    _get_queue_item_or_404(db, campaign_id, item_id)
    try:
        return cancel_queue_item(db, item_id, reason=(body.reason if body else None))
    except QueueServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}/queue-items/{item_id}/retry",
    response_model=DeliveryQueueItemRead,
)
def retry_delivery_queue_item(
    campaign_id: uuid.UUID,
    item_id: uuid.UUID,
    _body: DeliveryQueueItemRetryBody | None = None,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> DeliveryQueueItem:
    _get_campaign_or_404(db, profile.id, campaign_id)
    _get_queue_item_or_404(db, campaign_id, item_id)
    try:
        return retry_now(db, item_id)
    except QueueServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
