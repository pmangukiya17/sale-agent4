"""
One read-only aggregation endpoint powering the Delivery module's
first-time onboarding checklist (Connect mailbox -> Create Sending
Profile -> Create Campaign -> Send first email -> Delivery Ready).
Deliberately its own tiny route file rather than bolted onto
provider_connections.py/sending_profiles.py/delivery_campaigns.py - it
reads across all three of those plus DeliveryQueueItem, and none of them
individually own "how is onboarding going" as a concept. No new tables,
no new write path, no change to how any of the four underlying things get
created - this only ever answers "does at least one of X exist yet."
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.delivery_campaign import DeliveryCampaign
from app.models.delivery_queue_item import DeliveryQueueItem
from app.models.enums import DeliveryQueueItemStatus, ProviderConnectionStatus
from app.models.provider_connection import ProviderConnection
from app.models.sending_profile import SendingProfile
from app.schemas.delivery_onboarding import DeliveryOnboardingStatusRead

router = APIRouter()


@router.get(
    "/company-profiles/{company_profile_id}/delivery-onboarding-status",
    response_model=DeliveryOnboardingStatusRead,
)
def get_delivery_onboarding_status(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> DeliveryOnboardingStatusRead:
    has_connected_mailbox = (
        db.scalar(
            select(ProviderConnection.id)
            .where(
                ProviderConnection.company_profile_id == profile.id,
                ProviderConnection.status == ProviderConnectionStatus.CONNECTED,
            )
            .limit(1)
        )
        is not None
    )
    has_sending_profile_with_mailbox = (
        db.scalar(
            select(SendingProfile.id)
            .where(
                SendingProfile.company_profile_id == profile.id,
                SendingProfile.provider_connection_id.is_not(None),
            )
            .limit(1)
        )
        is not None
    )
    has_campaign = (
        db.scalar(select(DeliveryCampaign.id).where(DeliveryCampaign.company_profile_id == profile.id).limit(1))
        is not None
    )
    has_sent_email = (
        db.scalar(
            select(DeliveryQueueItem.id)
            .where(
                DeliveryQueueItem.company_profile_id == profile.id,
                DeliveryQueueItem.status == DeliveryQueueItemStatus.SENT,
            )
            .limit(1)
        )
        is not None
    )
    return DeliveryOnboardingStatusRead(
        has_connected_mailbox=has_connected_mailbox,
        has_sending_profile_with_mailbox=has_sending_profile_with_mailbox,
        has_campaign=has_campaign,
        has_sent_email=has_sent_email,
    )
