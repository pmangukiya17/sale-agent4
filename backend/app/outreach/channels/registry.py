"""
Channel provider registry: the one place a new channel renderer gets wired
in - exact mirror of Discovery/Research's provider registry.py. Adding a
channel (LinkedIn, WhatsApp, phone script, meeting request, ...) is adding
an import + a dict entry here - no schema change, no change anywhere else
in the pipeline.
"""
from app.outreach.channels.base import ChannelProvider
from app.outreach.channels.email_provider import EmailChannelProvider

CHANNEL_PROVIDER_REGISTRY: dict[str, type[ChannelProvider]] = {
    EmailChannelProvider.key: EmailChannelProvider,
}


def get_channel_provider(channel_key: str) -> ChannelProvider:
    provider_cls = CHANNEL_PROVIDER_REGISTRY.get(channel_key)
    if provider_cls is None:
        raise KeyError(f"Unknown outreach channel '{channel_key}'. Registered channels: {list(CHANNEL_PROVIDER_REGISTRY)}")
    return provider_cls()
