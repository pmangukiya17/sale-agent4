"""
GroqProviderClient - M11 (AI Provider Hierarchy). One example of Priority-2
("Free Cloud Providers") per the spec - see
docs/architecture/m11-ai-provider-hierarchy-plan.md Section 4.2. Groq's API
is itself OpenAI-compatible, so - exactly like LocalOllamaProviderClient -
this is a thin subclass of OpenAICompatibleProviderClient with a fixed,
documented base_url, not a bespoke SDK integration. Whether "groq" actually
behaves as a free-tier provider for a given deployment is a
PROVIDER_TIER_REGISTRY classification (app.ai_gateway.tiers), not
something this class asserts about itself - see that module's own
docstring for why tier membership is deliberately data, not code.
"""
from app.ai_gateway.providers.openai_compatible_client import OpenAICompatibleProviderClient
from app.core.config import settings

_PROVIDER_KEY = "groq"


class GroqProviderClient(OpenAICompatibleProviderClient):
    key = _PROVIDER_KEY

    @property
    def base_url(self) -> str | None:
        return settings.GROQ_BASE_URL

    @property
    def api_key(self) -> str | None:
        return settings.GROQ_API_KEY

    @property
    def default_model(self) -> str | None:
        return settings.GROQ_DEFAULT_MODEL

    def is_configured(self) -> bool:
        # Unlike the local client, Groq is a real hosted cloud service - an
        # API key is required, not optional.
        return bool(self.api_key) and bool(self.base_url)
