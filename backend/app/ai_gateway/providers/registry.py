"""
PROVIDER_CLIENT_REGISTRY - M7.2. Direct-import registry, NOT the
self-registration pattern ACTION_REGISTRY/AGENT_REGISTRY use - and that
difference is deliberate, not an inconsistency. This file lives WITHIN
the AI Gateway's own package, so it's allowed to import its own sibling
provider clients directly - exactly the same reasoning
app.delivery.providers.registry.PROVIDER_REGISTRY and
app.reply_intelligence.classifiers.registry.REPLY_CLASSIFIER_REGISTRY
already rely on. Self-registration exists specifically for registries
whose concrete implementations live OUTSIDE the registry's own package
(ACTION_REGISTRY's domain-owned Actions, AGENT_REGISTRY's domain-owned
Agents) - Provider Clients are not that; they're owned by, and live
inside, app.ai_gateway.providers itself.

Structural boundary this registry is the single, intentional exception
to: app/ai_gateway/providers/*_client.py are the ONLY files in this
codebase permitted to import anthropic/openai/google.genai directly.
Enforceable the same way the Workflow Engine's own domain boundary is -
via a repeatable grep check:

    grep -rlE "^\s*(import|from)\s+(anthropic|openai|google\.genai)" app/ \
      | grep -v "^app/ai_gateway/providers/"

should always return nothing.
"""
from app.ai_gateway.providers.base import ProviderClient
from app.ai_gateway.providers.claude_client import ClaudeProviderClient
from app.ai_gateway.providers.gemini_client import GeminiProviderClient
from app.ai_gateway.providers.groq_client import GroqProviderClient
from app.ai_gateway.providers.local_client import LocalOllamaProviderClient
from app.ai_gateway.providers.openai_client import OpenAIProviderClient

# M9 (AI Provider Hierarchy) adds LocalOllamaProviderClient/GroqProviderClient
# - both subclass OpenAICompatibleProviderClient (imports `openai`, not a new
# SDK) rather than adding a new permitted-import file; the grep rule in this
# docstring's header still holds unchanged.
PROVIDER_CLIENT_REGISTRY: dict[str, type[ProviderClient]] = {
    ClaudeProviderClient.key: ClaudeProviderClient,
    OpenAIProviderClient.key: OpenAIProviderClient,
    GeminiProviderClient.key: GeminiProviderClient,
    LocalOllamaProviderClient.key: LocalOllamaProviderClient,
    GroqProviderClient.key: GroqProviderClient,
}


def get_provider_client(provider_key: str) -> ProviderClient:
    provider_cls = PROVIDER_CLIENT_REGISTRY.get(provider_key)
    if provider_cls is None:
        raise KeyError(f"Unknown provider '{provider_key}'. Registered: {sorted(PROVIDER_CLIENT_REGISTRY)}")
    return provider_cls()
