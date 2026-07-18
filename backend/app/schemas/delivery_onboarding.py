from pydantic import BaseModel


class DeliveryOnboardingStatusRead(BaseModel):
    """Four cheap existence checks, one per onboarding step - powers the
    Delivery module's first-time checklist (DeliveryOnboarding.tsx).
    Deliberately read-only and derived entirely from data that already
    exists (ProviderConnection/SendingProfile/DeliveryCampaign/
    DeliveryQueueItem) - this adds a view, not a new concept, and changes
    nothing about how those four things are created. "Delivery Ready" is
    not its own field: the frontend derives it as
    has_connected_mailbox && has_sending_profile_with_mailbox &&
    has_campaign && has_sent_email, so there is exactly one source of
    truth for what each step means, not two copies that could drift."""

    has_connected_mailbox: bool
    has_sending_profile_with_mailbox: bool
    has_campaign: bool
    has_sent_email: bool
