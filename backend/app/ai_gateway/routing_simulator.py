"""
routing_simulator.py - M8.3 (AI Gateway Management & Control, Step 4 -
Routing Simulator). Pure, read-only derivation of a full, EXPLAINED
routing decision - "what would happen, and why" - reusing
`router.py`'s/`capabilities.py`'s own already-pure building blocks, never
re-implementing routing logic. This module NEVER attempts a real
provider call, never mutates anything, and never even imports
`app.core.config.settings` or sqlalchemy at module level - the exact
"testable without pydantic_settings installed" discipline
`router.py`/`capabilities.py`/`tiers.py` already established. The IMPURE
glue (reading live `settings.AI_MODE`, `PROVIDER_CLIENT_REGISTRY`,
`is_configured()`, `default_model`, and the provider-default price table)
lives in `app.ai_gateway.ui_query.simulate_routing()`, the one real
caller - same "pure core, impure shell" split
`app.ai_gateway.local_model_policy`'s own `resolve_local_model()` (pure
branching) vs. its DB-touching `list_model_roles()`/`save_model_role()`
siblings already established (Step 3's most recent precedent).

CEO-approved scope (Step 4, 2026-07-28): READ-ONLY. Explains a decision,
never executes one - `build_simulation()` never calls `ProviderClient.complete()`,
never writes to any table, never changes `AI_MODE`/any provider's
`enabled` flag. Shows the COMPLETE candidate chain (local + free +
premium, in preference order) rather than stopping at the first reached
provider, the way `ui_query._routing_preview_for_capability()` (M8.2,
still used by the pre-existing `GET /ai-gateway/routing` "live preview"
endpoint, unchanged by this step) does - every candidate gets a node with
a state/reason here, including ones that would never actually be
attempted (`skipped_not_reached`). Accepts hypothetical AI_MODE / per-
provider "as if configured/disabled" overrides (via `simulate_routing()`'s
own parameters - see that function) so an admin can ask "what would
happen if..." without touching any real setting.

Deliberately does its OWN capability filtering (via
`capabilities.filter_capable()`) on the PRE-filter `RoutingDecision`
(straight from `router._build_decision()`), rather than accepting an
already-filtered one from `router.ProviderRouter.select()` - specifically
so a capability-mismatch exclusion can be attached to a NODE at its
correct original position/role for display, instead of silently
vanishing the way real routing's own post-filtering (correctly, for ITS
purpose) already does.
"""
from dataclasses import dataclass, field
from typing import Callable

from app.ai_gateway.capabilities import ProviderCapabilities, RequiredCapabilities, filter_capable, resolve_capabilities
from app.ai_gateway.router import RoutingDecision

_CAPABILITY_LABELS: dict[str, str] = {
    "structured_output": "structured output",
    "tool_calling": "tool calling",
    "reasoning_support": "deep reasoning",
}


@dataclass(frozen=True)
class SimulationNode:
    """One candidate provider_key in the FULL preference order for this
    capability (local + free + premium) - never filtered out of the
    result, even when `state` is one of the "skipped_*" values. `role` is
    "primary" (position 0 of the auto-attempted chain), "fallback" (any
    later chain position), or "premium" (gated behind approval unless the
    gate is disabled or AI_MODE already folded premium into the chain -
    see `router._build_decision()`'s own docstring)."""

    provider_key: str
    tier: str
    role: str
    position: int
    state: str
    reason: str
    configured: bool
    overridden: bool
    cost_per_1k_input_usd: float | None = None
    cost_per_1k_output_usd: float | None = None
    estimated_cost_usd: float | None = None


@dataclass(frozen=True)
class SimulationResult:
    nodes: list[SimulationNode] = field(default_factory=list)
    outcome: str = "failed"
    outcome_detail: str = ""
    capability_excluded: list[str] = field(default_factory=list)


def _missing_capability_labels(caps: ProviderCapabilities, required: RequiredCapabilities) -> list[str]:
    missing = []
    if required.structured_output and not caps.structured_output:
        missing.append(_CAPABILITY_LABELS["structured_output"])
    if required.tool_calling and not caps.tool_calling:
        missing.append(_CAPABILITY_LABELS["tool_calling"])
    if required.reasoning_support and not caps.reasoning_support:
        missing.append(_CAPABILITY_LABELS["reasoning_support"])
    return missing


def build_simulation(
    decision: RoutingDecision,
    required: RequiredCapabilities,
    *,
    provider_level: dict[str, ProviderCapabilities],
    is_configured: Callable[[str], bool],
    require_premium_approval: bool,
    tier_of: Callable[[str], str],
    label_of: Callable[[str], str],
    price_of: Callable[[str], tuple[float | None, float | None]],
    estimate_cost: Callable[[str], float | None],
    overrides: dict[str, bool] | None = None,
) -> SimulationResult:
    """The pure core every real caller (`ui_query.simulate_routing()`) and
    every test in `tests/test_routing_simulator_pure.py` exercises
    identically - every "impure" fact (real `is_configured()`, real
    prices, real `settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL`) is
    supplied by the caller as a plain value/callable, never read directly
    by this function.

    `overrides` is a SEPARATE, purely-additive simulation layer, never a
    replacement for `is_configured`: a provider_key present in `overrides`
    has its EFFECTIVE (hypothetical) configured state taken from there
    instead of `is_configured(key)`, with `overridden=True` recorded on
    its node so a caller can visually distinguish a real fact from a
    simulated one. A provider_key absent from `overrides` is completely
    unaffected - real state, real `is_configured(key)` value,
    `overridden=False`. This is the ONE thing `simulate_routing()` lets a
    caller hypothesize about per-provider; `decision` itself already
    encodes whatever AI_MODE was requested (real or hypothetical - see
    that function's own docstring), so this function never needs its own
    AI_MODE parameter.

    `decision` is expected to be the PRE-capability-filter
    `RoutingDecision` (straight from `router._build_decision()`, NOT
    `router.ProviderRouter.select()`'s already-filtered result) - see
    module docstring for why."""
    overrides = overrides or {}

    capable_chain, excluded_chain = filter_capable(decision.chain(), required, model=None, provider_level=provider_level)
    capable_premium, excluded_premium = filter_capable(decision.premium, required, model=None, provider_level=provider_level)
    excluded_set = set(excluded_chain) | set(excluded_premium)

    nodes: list[SimulationNode] = []
    reached = False
    outcome = "failed"
    outcome_detail = "No configured, capable provider is available for this capability."

    def _real_configured(key: str) -> bool:
        return bool(is_configured(key))

    def _effective_configured(key: str) -> bool:
        return overrides[key] if key in overrides else _real_configured(key)

    def _make_node(key: str, role: str, position: int, *, state: str, reason: str, estimated_cost_usd: float | None = None) -> SimulationNode:
        prompt_price, completion_price = price_of(key)
        return SimulationNode(
            provider_key=key,
            tier=tier_of(key),
            role=role,
            position=position,
            state=state,
            reason=reason,
            configured=_real_configured(key),
            overridden=key in overrides,
            cost_per_1k_input_usd=prompt_price,
            cost_per_1k_output_usd=completion_price,
            estimated_cost_usd=estimated_cost_usd,
        )

    ordered_candidates = [(key, "primary" if i == 0 else "fallback") for i, key in enumerate(decision.chain())]
    ordered_candidates += [(key, "premium") for key in decision.premium]

    for position, (key, role) in enumerate(ordered_candidates):
        label = label_of(key)

        if key in excluded_set:
            caps = resolve_capabilities(key, None, provider_level=provider_level)
            missing = _missing_capability_labels(caps, required)
            missing_text = " and ".join(missing) if missing else "a required capability"
            nodes.append(
                _make_node(
                    key,
                    role,
                    position,
                    state="skipped_capability_mismatch",
                    reason=f"{label} doesn't support {missing_text}, which this request requires.",
                )
            )
            continue

        if reached:
            nodes.append(
                _make_node(
                    key,
                    role,
                    position,
                    state="skipped_not_reached",
                    reason=f"An earlier provider already satisfied this request; {label} would not be reached.",
                )
            )
            continue

        overridden_note = " (simulated override)" if key in overrides else ""

        if not _effective_configured(key):
            nodes.append(
                _make_node(
                    key, role, position, state="skipped_not_configured", reason=f"{label} is not configured{overridden_note}."
                )
            )
            continue

        estimated_cost_usd = estimate_cost(key)

        if role == "premium" and require_premium_approval:
            reached = True
            outcome = "waiting"
            outcome_detail = f"{label} would require your explicit premium approval before use."
            nodes.append(
                _make_node(
                    key,
                    role,
                    position,
                    state="requires_approval",
                    reason=(
                        f"Local/free tier exhausted for this capability{overridden_note}. {label} would require "
                        "your explicit approval before use."
                    ),
                    estimated_cost_usd=estimated_cost_usd,
                )
            )
        else:
            reached = True
            outcome = "success"
            if role == "premium":
                outcome_detail = f"{label} would be used (premium approval gate is disabled)."
                reason = f"{label} is configured{overridden_note} and the premium approval gate is disabled - this is the provider that would actually be used."
            else:
                outcome_detail = f"{label} is configured{overridden_note} and would serve this request."
                reason = f"{label} is configured{overridden_note} and next in the chain - this is the provider that would actually be used."
            nodes.append(_make_node(key, role, position, state="would_call", reason=reason, estimated_cost_usd=estimated_cost_usd))

    return SimulationResult(
        nodes=nodes,
        outcome=outcome,
        outcome_detail=outcome_detail,
        capability_excluded=sorted(excluded_set),
    )
