"""
Provider registry - exact mirror of discovery/providers/registry.py and
outreach/channels/registry.py. Adding SMTP/SES/SendGrid/Mailgun later is
an import + a dict entry here, never a schema change and never a change
to connection_service/dispatch_service.
"""
from app.delivery.providers.base import EmailConnectionProvider
from app.delivery.providers.gmail_provider import GmailProvider
from app.delivery.providers.outlook_provider import OutlookProvider

PROVIDER_REGISTRY: dict[str, type[EmailConnectionProvider]] = {
    GmailProvider.key: GmailProvider,
    OutlookProvider.key: OutlookProvider,
}


def get_provider(provider_key: str) -> EmailConnectionProvider:
    provider_cls = PROVIDER_REGISTRY.get(provider_key)
    if provider_cls is None:
        raise KeyError(f"Unknown delivery provider '{provider_key}'. Registered providers: {list(PROVIDER_REGISTRY)}")
    return provider_cls()
