"""
Token/cost accounting - M7.2. Deliberately simple: a plain, code-based
$/1K-token price table keyed by (provider_key, model), read by
estimate_cost_usd() below. Not a database table - pricing changes at
least as often as model catalogs do, and nothing yet consumes historical
cost data in a way that would justify persisting it (no cost dashboard
exists - see the approved architecture's own "future milestone" framing
for that). A future milestone that needs durable cost history can add
that without this module's own interface changing - callers already
receive a TokenUsage with cost_usd populated (or None, if the model
isn't in the table); persisting it is entirely the CALLER's choice, not
something this module does itself.

Unknown (provider_key, model) pairs return cost_usd=None rather than
raising or guessing - an unpriced model is a normal, expected state
(this table will always lag real provider catalogs), not an error.
"""
from app.ai_gateway.request import TokenUsage

# USD per 1,000 tokens, (prompt_price, completion_price). Deliberately
# small and incomplete - populated only for the models this project has
# actually configured a DEFAULT_MODEL for (see app.core.config.settings)
# plus a couple of common reference points; extend as real usage
# accumulates, not speculatively ahead of it.
_PRICE_TABLE_USD_PER_1K: dict[tuple[str, str], tuple[float, float]] = {}


def register_price(provider_key: str, model: str, *, prompt_price_per_1k: float, completion_price_per_1k: float) -> None:
    """Adds/overwrites one (provider_key, model) price entry - a plain
    code-level table, not a registry with a duplicate-key guard (unlike
    ACTION_REGISTRY/AGENT_REGISTRY): re-registering the same model with
    an updated price is an expected, normal operation as providers
    change their pricing, not a bug to guard against."""
    _PRICE_TABLE_USD_PER_1K[(provider_key, model)] = (prompt_price_per_1k, completion_price_per_1k)


def estimate_cost_usd(*, provider_key: str, model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    prices = _PRICE_TABLE_USD_PER_1K.get((provider_key, model))
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
