"""
LocalOllamaProviderClient - M11 (AI Provider Hierarchy). Priority-1 ("always
the default") provider per the AI Provider Hierarchy spec - see
docs/architecture/m11-ai-provider-hierarchy-plan.md Section 4.2 for why this
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

M8.2 addendum (approved 2026-07-28): overrides `_resolve_model()` (see
`OpenAICompatibleProviderClient`'s own docstring for that hook) to make
model selection CAPABILITY-aware instead of always returning
`self.default_model` - e.g. a "writing" task (`outreach_email_generation`)
prefers `LOCAL_MODEL_SECONDARY_MODEL` (e.g. llama3.1:8b) over
`LOCAL_MODEL_DEFAULT_MODEL` (e.g. qwen3:8b). All of the actual policy
(which capability prefers which semantic role, which role maps to which
setting) lives in `app.ai_gateway.local_model_policy` - this override is
intentionally three lines; it is the ONLY place in this codebase that
calls `resolve_local_model()`. `GroqProviderClient` does NOT override
this - it has no task-based local-model policy (Groq is a single hosted
model per deployment, not a local server running several).

`request.model` (an explicit caller-supplied override) still wins over
everything here, unchanged from M11's original behavior - this override
only ever fires when `request.model` is None, which is every real caller
in this codebase today (see `capabilities.py`'s own disclosed-limitation
note).
"""
from app.ai_gateway.local_model_policy import resolve_local_model
from app.ai_gateway.providers.openai_compatible_client import OpenAICompatibleProviderClient
from app.ai_gateway.request import GatewayRequest
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

    def _resolve_model(self, request: GatewayRequest) -> str | None:
        if request.model:
            return request.model
        return resolve_local_model(request.capability) or self.default_model
