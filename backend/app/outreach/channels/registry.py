"""
Channel provider registry: the one place a new channel renderer gets wired
in - exact mirror of Discovery/Research's provider registry.py. Adding a
channel (LinkedIn, WhatsApp, phone script, meeting request, ...) is adding
an import + a dict entry here - no schema change, no change anywhere else
in the pipeline.

M-AIGW-5 addition (Outreach as the Gateway's second production consumer -
see docs/architecture/provider-neutral-ai-gateway-plan.md Section 12):
CHANNEL_BACKEND_REGISTRY below adds a SECOND, orthogonal selection axis -
which RENDERING BACKEND a channel uses - mirroring
research/analysis/registry.py's ANALYSIS_ENGINE_REGISTRY/
RESEARCH_ANALYSIS_ENGINE_BACKEND pattern exactly. Only "email" has more
than one backend today; CHANNEL_PROVIDER_REGISTRY above is untouched and
still the sole resolution path for every other channel_key.
"""
from app.core.config import settings
from app.outreach.channels.base import ChannelProvider
from app.outreach.channels.email_provider import EmailChannelProvider
from app.outreach.channels.llm_email_provider import LLMEmailChannelProvider

CHANNEL_PROVIDER_REGISTRY: dict[str, type[ChannelProvider]] = {
    EmailChannelProvider.key: EmailChannelProvider,
}

# channel_key -> {backend_key: ChannelProvider class}. A channel_key
# present here is resolved through this dict + its own settings flag
# INSTEAD of CHANNEL_PROVIDER_REGISTRY above; a channel_key absent from
# this dict (every channel except "email" today) is resolved directly via
# CHANNEL_PROVIDER_REGISTRY, unchanged. Default backend for "email" stays
# "deterministic" (EmailChannelProvider) - byte-for-byte the pre-M-AIGW-5
# behavior - matching RESEARCH_ANALYSIS_ENGINE_BACKEND's own original
# Phase 3 rollout convention (default the existing stub first; flipping
# the default is a separate, later, explicitly-approved decision).
CHANNEL_BACKEND_REGISTRY: dict[str, dict[str, type[ChannelProvider]]] = {
    "email": {
        "deterministic": EmailChannelProvider,
        "llm": LLMEmailChannelProvider,
    },
}

# channel_key -> the settings attribute name that selects its backend.
_CHANNEL_BACKEND_SETTING: dict[str, str] = {
    "email": "OUTREACH_EMAIL_CHANNEL_BACKEND",
}


def get_channel_provider(channel_key: str) -> ChannelProvider:
    backend_options = CHANNEL_BACKEND_REGISTRY.get(channel_key)
    if backend_options is not None:
        setting_name = _CHANNEL_BACKEND_SETTING[channel_key]
        backend_key = getattr(settings, setting_name)
        provider_cls = backend_options.get(backend_key)
        if provider_cls is None:
            raise KeyError(f"Unknown '{channel_key}' channel backend '{backend_key}'. Registered backends: {list(backend_options)}")
        return provider_cls()

    provider_cls = CHANNEL_PROVIDER_REGISTRY.get(channel_key)
    if provider_cls is None:
        raise KeyError(f"Unknown outreach channel '{channel_key}'. Registered channels: {list(CHANNEL_PROVIDER_REGISTRY)}")
    return provider_cls()
