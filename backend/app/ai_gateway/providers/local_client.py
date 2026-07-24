"""
LocalOllamaProviderClient - M9 (AI Provider Hierarchy). Priority-1 ("always
the default") provider per the AI Provider Hierarchy spec - see
docs/architecture/ai-provider-hierarchy-v3-plan.md Section 4.2 for why this
is a thin, otherwise-empty subclass of OpenAICompatibleProviderClient
rather than a bespoke Ollama SDK integration: Ollama's own API already
implements the OpenAI chat-completions wire format at /v1, so pointing the
`openai` SDK at LOCAL_MODEL_BASE_URL (e.g. "http://localhost:11434/v1") is
a complete integration. Naming this "local_ollama" rather than plain
"local" is deliberate - Section 4.1's tier registry is what determines
"local" tier membership; this provider_key names the concrete adapter
(which happens to work with Ollama, vLLM, LM Studio, or anything else
speaking the same wire protocol at whatever base_url an operator points it
at - "Ollama" is this project's reference example, not a hard dependency
on Ollama specifically).
"""
from app.ai_gateway.providers.openai_compatible_client import OpenAICompatibleProviderClient
from app.core.config import settings

_PROVIDER_KEY = "local_ollama"


class LocalOllamaProviderClient(OpenAICompatibleProviderClient):
    key = _PROVIDER_KEY

    @property
    def base_url(self) -> str | None:
        return settings.LOCAL_MODEL_BASE_URL

    @property
    def api_key(self) -> str | None:
        return settings.LOCAL_MODEL_API_KEY

    @property
    def default_model(self) -> str | None:
        return settings.LOCAL_MODEL_DEFAULT_MODEL
