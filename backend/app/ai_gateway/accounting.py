"""
Token/cost accounting - M7.2, extended by M-AIGW-4 (Cost Registry - see
docs/architecture/provider-neutral-ai-gateway-plan.md Section 11).
Deliberately simple: a plain, code-based $/1K-token price table, read by
estimate_cost_usd() below. Not a database table - pricing changes at
least as often as model catalogs do, and nothing yet consumes historical
cost data in a way that would justify persisting it (no cost dashboard
exists - see the approved architecture's own "future milestone" framing
for that). A future milestone that needs durable cost history can add
that without this module's own interface changing - callers already
receive a TokenUsage with cost_usd populated (or None, if truly nothing
is priced for that provider); persisting it is entirely the CALLER's
choice, not something this module does itself.

Centralized, Gateway-owned metadata (M-AIGW-4 decision): this remains the
ONE place price numbers live in this codebase - no ProviderClient (see
providers/*_client.py) declares its own pricing, mirroring exactly how
ProviderCapabilities keeps protocol facts off of pricing and tiers.py
keeps tier assignment off of ProviderClient too. Adding a price for a new
provider/model means editing THIS file only, never touching a provider
client.

Independent from routing (M-AIGW-4 decision): nothing in this module is
imported by router.py, and nothing in router.py's
CAPABILITY_PROVIDER_PREFERENCE/RoutingDecision/partition-by-tier logic
reads a price - confirmed via `grep -n "accounting" app/ai_gateway/router.py`
returning nothing. Price is informational (pre-call estimates for the
premium-approval prompt, post-call actuals on TokenUsage) and a soft
budget-check input (client.py's own `_check_soft_budget` - logs a
warning, never blocks a call) - never a routing input. A future cost-aware
policy engine can read `estimate_cost_usd()`/`estimate_pre_call_cost_usd()`
directly without this module changing.

Two-level, model-aware keying (M-AIGW-4 decision, mirroring
capabilities.py's own two-level ProviderCapabilities/`_CAPABILITY_OVERRIDES`
split): `_PROVIDER_DEFAULT_PRICE_USD_PER_1K` is one price per provider_key -
"whatever this provider's typical current-generation model costs" - and
`_MODEL_PRICE_OVERRIDES_USD_PER_1K` is the pre-existing exact
(provider_key, model) table, checked FIRST and falling back to the
provider default. This exists because `settings.<PROVIDER>_DEFAULT_MODEL`
(config.py) is an operator-chosen, freely-configurable string this
codebase cannot predict - a price table keyed ONLY by exact model id
requires re-registering every time an operator bumps their configured
model to a newer id, and silently reverts to cost_usd=None the moment
they do (the exact "structurally complete but functionally inert in
production" gap recorded in this project's AI-layer architecture review).
A provider-level default closes that gap with a disclosed
APPROXIMATION rather than an exact figure for whichever specific model is
actually configured.

Unknown (provider_key, model) pairs with no provider-level default either
still return cost_usd=None rather than raising or guessing - an unpriced
provider is a normal, expected state (this table will always lag real
provider catalogs, and a not-yet-classified provider_key has neither
entry), not an error.

Sourcing/staleness disclosure (M-AIGW-4): `_PROVIDER_DEFAULT_PRICE_USD_PER_1K`
and `_MODEL_PRICE_OVERRIDES_USD_PER_1K` below are populated from each
provider's own official pricing page, web-verified at implementation time
(July 2026) - see each entry's own comment for the specific model/page.
Provider pricing changes regularly; treat every number here as an
estimate for a premium-approval prompt or a soft budget check, never as
an authoritative invoice - re-verify against the provider's live pricing
page before using this for a real budget decision.
"""
from app.ai_gateway.request import TokenUsage

# Provider-level DEFAULT price - USD per 1,000 tokens, (prompt_price,
# completion_price) - see module docstring for why this tier of the table
# exists. One entry per provider_key registered in
# app.ai_gateway.providers.registry.PROVIDER_CLIENT_REGISTRY; a
# provider_key not yet added here (e.g. a future sixth provider) simply
# has no default, same "unpriced is normal" convention as before.
_PROVIDER_DEFAULT_PRICE_USD_PER_1K: dict[str, tuple[float, float]] = {
    # Claude Sonnet-class - the tier this codebase's own
    # ANTHROPIC_DEFAULT_MODEL is expected to be set to for typical
    # production use. Source: docs.claude.com/en/docs/about-claude/pricing
    # ("Claude Sonnet 4.6"/"Claude Sonnet 4.5" standard rate; Sonnet 5's
    # $2/$10 introductory rate expires 2026-08-31 and reverts to this
    # same $3/$15, so the steady-state figure is used here rather than
    # the temporary one).
    "claude": (3.0, 15.0),
    # GPT-5.6 Terra - OpenAI's current mid-tier flagship, standard/short-
    # context pricing. Source: developers.openai.com/api/docs/pricing.
    "openai": (2.5, 15.0),
    # Gemini 3.1 Pro Preview, paid tier, standard, <=200k-token prompts -
    # the paid "gemini" key's typical flagship (long-context (>200k)
    # prompts cost more; not modeled here, informational estimate only).
    # Source: ai.google.dev/gemini-api/docs/pricing.
    "gemini": (2.0, 12.0),
    # AI Studio free tier is genuinely $0 while within its (separate,
    # non-dollar) rate-limit quota - and Pro-class models are explicitly
    # NOT available on the free tier at all per Google's own pricing page,
    # so this provider_key only ever actually serves Flash-class models
    # in practice regardless; $0/$0 is the correct estimate either way
    # (matches tiers.py's own FREE classification for this provider_key).
    "gemini_ai_studio": (0.0, 0.0),
    # Llama 3.3 70B Versatile - Groq's general-purpose flagship. Source:
    # groq.com/pricing.
    "groq": (0.59, 0.79),
    # Self-hosted - no per-token API cost regardless of which local model
    # an operator points LOCAL_MODEL_BASE_URL at.
    "local_ollama": (0.0, 0.0),
}

# (provider_key, model) -> price override - checked FIRST, before falling
# back to the provider-level default above, for when the operator's
# configured model happens to match one of these exactly. Same
# keying/"re-registering is normal" semantics this table has always had
# (pre-M-AIGW-4 this WAS the only table); a handful of named per-model
# entries are populated below as concrete, disclosed examples of the
# override mechanism actually mattering - not an attempt at exhaustive
# catalog coverage, which would go stale immediately (see module
# docstring's own staleness disclosure).
_MODEL_PRICE_OVERRIDES_USD_PER_1K: dict[tuple[str, str], tuple[float, float]] = {
    # Anthropic pricing page, standard rate.
    ("claude", "claude-opus-4-5"): (5.0, 25.0),
    ("claude", "claude-haiku-4-5"): (1.0, 5.0),
    # developers.openai.com/api/docs/pricing, "Standard", short context.
    ("openai", "gpt-5.6-sol"): (5.0, 30.0),
    ("openai", "gpt-5.6-luna"): (1.0, 6.0),
    # ai.google.dev/gemini-api/docs/pricing, "Gemini 3.6 Flash", paid
    # tier, standard.
    ("gemini", "gemini-3.6-flash"): (1.5, 7.5),
    # groq.com/pricing.
    ("groq", "llama-3.1-8b-instant"): (0.05, 0.08),
}


def register_price(provider_key: str, model: str, *, prompt_price_per_1k: float, completion_price_per_1k: float) -> None:
    """Adds/overwrites one (provider_key, model) price OVERRIDE - a plain
    code-level table, not a registry with a duplicate-key guard (unlike
    ACTION_REGISTRY/AGENT_REGISTRY): re-registering the same model with
    an updated price is an expected, normal operation as providers
    change their pricing, not a bug to guard against."""
    _MODEL_PRICE_OVERRIDES_USD_PER_1K[(provider_key, model)] = (prompt_price_per_1k, completion_price_per_1k)


def register_provider_default_price(provider_key: str, *, prompt_price_per_1k: float, completion_price_per_1k: float) -> None:
    """M-AIGW-4 addition. Adds/overwrites one provider_key's DEFAULT
    price - used by estimate_cost_usd() whenever no more specific
    (provider_key, model) override exists for the exact model actually in
    use. Same "re-registering is normal" convention as register_price()
    above."""
    _PROVIDER_DEFAULT_PRICE_USD_PER_1K[provider_key] = (prompt_price_per_1k, completion_price_per_1k)


def estimate_cost_usd(*, provider_key: str, model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    prices = _MODEL_PRICE_OVERRIDES_USD_PER_1K.get((provider_key, model))
    if prices is None:
        prices = _PROVIDER_DEFAULT_PRICE_USD_PER_1K.get(provider_key)
    if prices is None:
        return None
    prompt_price_per_1k, completion_price_per_1k = prices
    return round((prompt_tokens / 1000) * prompt_price_per_1k + (completion_tokens / 1000) * completion_price_per_1k, 6)


def estimate_pre_call_cost_usd(
    *, provider_key: str, model: str, prompt_char_length: int, expected_completion_tokens: int = 1024
) -> float | None:
    """M11 (AI Provider Hierarchy). A rough, BEFORE-the-call cost estimate,
    for the premium-approval prompt ("Estimated API cost: ~$0.xx") - unlike
    estimate_cost_usd() above, which needs real token counts that only
    exist after a call completes. Uses a standard, approximate
    chars-per-token heuristic (~4 characters/token for English prose) -
    disclosed as approximate, not exact, since the real tokenizer isn't
    invoked here. `expected_completion_tokens` defaults to a conservative
    round number when the caller has no better estimate (e.g. from
    ExecutionPolicy.max_tokens); pass that through when it's known.
    Returns None under the same "unpriced model" convention as
    estimate_cost_usd() - an approval prompt with no cost estimate is
    valid (it just can't show a dollar figure), never an error."""
    estimated_prompt_tokens = max(1, prompt_char_length // 4)
    return estimate_cost_usd(
        provider_key=provider_key,
        model=model,
        prompt_tokens=estimated_prompt_tokens,
        completion_tokens=expected_completion_tokens,
    )


def build_usage(*, provider_key: str, model: str, prompt_tokens: int, completion_tokens: int) -> TokenUsage:
    """The one place a ProviderClient should construct its TokenUsage -
    keeps the estimate_cost_usd() call from being duplicated three times
    (once per provider client)."""
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_usd=estimate_cost_usd(
            provider_key=provider_key, model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        ),
    )
