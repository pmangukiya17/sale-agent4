"""
Provider tier classification - M11 (AI Provider Hierarchy). Deliberately a
plain dict, not a property of any ProviderClient class - which provider_key
is "local"/"free"/"premium" is a RESERVATION/DEPLOYMENT decision (which
bucket an operator puts a provider in), never something the code
special-cases by provider name. This is what makes "implement a generic
Free Cloud Provider abstraction, don't hardcode for Gemini/Groq
specifically" true in practice: the SAME provider_key (e.g. a Gemini AI
Studio key) can be registered as "free" here, or a Gemini paid key
registered as "premium" - the client code (GeminiProviderClient) never
knows or cares which.

See docs/architecture/m11-ai-provider-hierarchy-plan.md Section 4.1.

M-AIGW-3 (Gemini Free-Tier Split - see
docs/architecture/provider-neutral-ai-gateway-plan.md Section 7) makes the
"or, in a later phase, register it a second time" option below real:
`gemini_ai_studio` (a distinct provider_key, same underlying
GeminiProviderClient-family class - see gemini_client.py's own
`_GeminiProviderClientBase`) is classified FREE here, while the
pre-existing `gemini` (a paid key) stays PREMIUM, completely unchanged.
"""
import enum


class ProviderTier(str, enum.Enum):
    LOCAL = "local"
    FREE = "free"
    PREMIUM = "premium"


# provider_key -> tier. Every key here must also exist in
# app.ai_gateway.providers.registry.PROVIDER_CLIENT_REGISTRY - router.py's
# own partitioning logic treats an entry missing from THAT registry as a
# configuration error the same way it already does today (KeyError,
# logged, chain continues past it).
#
# Day-1 values: the three pre-existing cloud SDKs stay "premium" (matches
# today's actual behavior exactly - see AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL's
# own docstring for how this interacts with backward compatibility). The
# two M11 provider clients are classified per the spec's own hierarchy.
# M-AIGW-3 adds "gemini_ai_studio" (FREE) alongside the pre-existing
# "gemini" (PREMIUM, unchanged) - see gemini_client.py's own docstring for
# why these are two distinct provider_keys sharing one implementation
# rather than one key silently reclassified (a paid key and a free-tier
# key are genuinely different credentials/quotas, not the same
# configuration under two names).
PROVIDER_TIER_REGISTRY: dict[str, ProviderTier] = {
    "local_ollama": ProviderTier.LOCAL,
    "groq": ProviderTier.FREE,
    "gemini_ai_studio": ProviderTier.FREE,
    "claude": ProviderTier.PREMIUM,
    "openai": ProviderTier.PREMIUM,
    "gemini": ProviderTier.PREMIUM,
}


def tier_of(provider_key: str) -> ProviderTier:
    """Unknown provider_keys default to PREMIUM - the safe failure
    direction (an unclassified provider requires explicit approval rather
    than silently being auto-attempted as if it were free)."""
    return PROVIDER_TIER_REGISTRY.get(provider_key, ProviderTier.PREMIUM)


def partition(provider_keys: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Splits an ordered provider_key preference list into three groups -
    (local, free, premium) - preserving relative order within each group.
    This is the one function router.py's tier-aware select() calls - kept
    here, not duplicated in router.py, so PROVIDER_TIER_REGISTRY has
    exactly one reader. Three-way (not local+free combined) specifically
    so "local_only" mode can exclude free-tier cloud providers entirely -
    see router.py's _build_decision()."""
    local: list[str] = []
    free: list[str] = []
    premium: list[str] = []
    for key in provider_keys:
        tier = tier_of(key)
        if tier == ProviderTier.LOCAL:
            local.append(key)
        elif tier == ProviderTier.FREE:
            free.append(key)
        else:
            premium.append(key)
    return local, free, premium
