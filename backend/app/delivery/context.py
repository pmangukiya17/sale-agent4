"""
DeliveryContext: everything a DeliveryProvider.send() needs to dispatch
one queue item. Deliberately narrow compared to OutreachContext/
DiscoveryContext - a provider at send-time needs the sender identity, the
resolved credential, and the already-FROZEN content; it never re-reads
OutreachDraft, PersonalizationSnapshot, or anything upstream of the
DeliveryQueueItem. That is the concrete enforcement of "the provider layer
should never know about timezone calculations" and "M4 must never know
how delivery works" - this dataclass is the only thing a provider ever
sees, and it contains none of that upstream machinery.
"""
from dataclasses import dataclass

from app.models.delivery_queue_item import DeliveryQueueItem
from app.models.provider_connection import ProviderConnection
from app.models.sending_profile import SendingProfile


@dataclass
class DeliveryContext:
    queue_item: DeliveryQueueItem
    sending_profile: SendingProfile
    provider_connection: ProviderConnection
    # Decrypted {access_token, refresh_token, expires_at, ...} - resolved
    # by dispatch_service via a CredentialStore immediately before
    # building this context, held only in memory for the duration of one
    # dispatch call, never logged, never persisted anywhere else.
    credential_payload: dict
