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

M-AIGW-2 (Provider-Neutral AI Gateway foundation follow-up - see
docs/architecture/provider-neutral-ai-gateway-plan.md Section 3/5, and
the CEO's own decision recorded there: keep this direct-import registry,
do not rebuild it as a self-registering plugin system). Documentation-
only addition, no code change: the checklist for adding a NEW provider,
now that M-AIGW-1 added a fifth step (declaring capabilities). All five
edits are small, explicit, and each lives at the file a contributor would
naturally look in for that concern - nothing here is hidden behind
indirection or magic registration:

  1. Write the new `app/ai_gateway/providers/<name>_client.py` - a
     concrete `ProviderClient` subclass. If it speaks the OpenAI
     chat-completions wire format (most local/free providers do), prefer
     subclassing `OpenAICompatibleProviderClient` over a bespoke SDK
     integration (see that module's own docstring) - this is genuinely
     the common case, not just today's two examples.
  2. On that new class, declare `capabilities: ClassVar[ProviderCapabilities]`
     (see app.ai_gateway.capabilities' own docstring) reflecting what this
     provider's wire-format/SDK integration ACTUALLY supports - never
     copy another provider's declaration without checking. Leave
     `streaming=False` unless/until AIGateway.stream() itself is
     implemented (see client.py's own docstring for why declaring it True
     earlier would be dishonest - the Gateway can't deliver it yet
     regardless of what the SDK supports). Override `default_model` (a
     property, see providers/base.py's own docstring) to return this
     provider's own `settings.<PROVIDER>_DEFAULT_MODEL`-shaped value.
  3. Add the new class to `PROVIDER_CLIENT_REGISTRY` below (this file).
  4. Classify its tier in `app.ai_gateway.tiers.PROVIDER_TIER_REGISTRY`
     (local/free/premium - a deployment/reservation decision, see that
     module's own docstring for why it's data, not a property of the
     class itself).
  5. Add its `provider_key` to whichever `CAPABILITY_PROVIDER_PREFERENCE`
     entries (app.ai_gateway.router) should actually try it, in the
     right preference order - a brand new provider added to steps 3/4
     alone is NOT automatically tried by anything; a capability's
     preference list is the one place that decides "try this provider for
     this kind of request."

Plus, if the provider needs its own API key/base_url/default-model
settings (nearly always): add the `settings.<PROVIDER>_*` block to
`app/core/config.py`, following any existing provider's block as the
template (see that file's own AI Gateway section comments).

This checklist is deliberately NOT itself enforced by a test or CI check
- unlike the anthropic/openai/google.genai import boundary above, "did
you complete all 5 steps for provider X" has no single grep-able
invariant (a provider missing from CAPABILITY_PROVIDER_PREFERENCE, for
instance, is a valid, sometimes-intentional state - see that dict's own
docstring for "an agent with no specific entry... routes through the same
single-provider... default"). Treat this as a contributor checklist, not
a substitute for reviewing the diff.
"""
from app.ai_gateway.providers.base import ProviderClient
from app.ai_gateway.providers.claude_client import ClaudeProviderClient
from app.ai_gateway.providers.gemini_client import GeminiProviderClient
from app.ai_gateway.providers.groq_client import GroqProviderClient
from app.ai_gateway.providers.local_client import LocalOllamaProviderClient
from app.ai_gateway.providers.openai_client import OpenAIProviderClient

# M11 (AI Provider Hierarchy) adds LocalOllamaProviderClient/GroqProviderClient
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
