"""
Provider Router - M7.2, extended M11 (AI Provider Hierarchy). Decides WHICH
provider (and, if it fails, which to fall back to) serves a given
GatewayRequest, keyed by `request.capability` - never by agent_key, and
never known by anything above the AI Gateway (the approved architecture's
own "the rest of the system should never know which provider was
selected"). Deliberately a thin, swappable policy - see
CAPABILITY_PROVIDER_PREFERENCE's own comment for why this is a plain
Python dict rather than a database table.

M11 changes the SHAPE of the policy from "one provider, no fallback" to
"an ordered preference list, partitioned by tier and settings.AI_MODE" -
see docs/architecture/m11-ai-provider-hierarchy-plan.md Section 4.3 for the
full design. `RoutingDecision.chain()` keeps its exact M7.2 meaning (the
list AIGateway.complete() auto-attempts) - it's just no longer always
length 1. The NEW `premium` list is never auto-attempted by
AIGateway.complete() unless the request is already `premium_approved` or
settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL is False - see client.py's
own docstring for that gate.

`settings` is imported LAZILY (inside select(), not at module level) -
same "testable without pydantic_settings installed" discipline
client.py's own docstring already established for
app.ai_gateway.providers.registry. Every other piece of this module
(RoutingDecision, CAPABILITY_PROVIDER_PREFERENCE, partition-by-tier logic)
remains fully importable and testable without settings/pydantic_settings.

M-AIGW-1 (Provider-Neutral AI Gateway foundation) adds a further,
SEPARATE filtering pass on top of the above, applied only in select()
itself (never inside _build_decision(), which keeps its exact existing
signature/tests untouched - see tests/test_ai_provider_hierarchy_pure.py's
own TestBuildDecisionPerMode, none of which pass a GatewayRequest at all):
once _build_decision() has produced a tier/AI_MODE-shaped decision,
select() further drops any provider_key from chain()/premium whose
declared app.ai_gateway.capabilities.ProviderCapabilities don't satisfy
what THIS SPECIFIC request needs (derived from response_format/tools/
requires_deep_reasoning - see capabilities.derive_required_capabilities()).
This is a fast no-op (returns the decision completely unchanged) for
every request that doesn't require structured_output/tool_calling/
reasoning_support - i.e. every existing caller in this codebase today,
since none set requires_deep_reasoning and every currently-registered
provider already declares structured_output=True/tool_calling=True (see
each provider client's own _CAPABILITIES declaration) - so this is a real,
exercised code path for Research's actual JSON-schema traffic, not dead
code, but produces byte-for-byte the same RoutingDecision as before this
addition for every request in production today.
"""
from dataclasses import dataclass, field

from app.ai_gateway.capabilities import derive_required_capabilities, filter_capable
from app.ai_gateway.request import GatewayRequest
from app.ai_gateway.tiers import partition

_DEFAULT_CAPABILITY_KEY = "default"


@dataclass(frozen=True)
class RoutingDecision:
    # M11: primary is now OPTIONAL - str for every M7.2 test/caller
    # constructing RoutingDecision(primary="something") unchanged, but
    # None is a legitimate M11 state ("nothing to auto-attempt, everything
    # is gated behind premium approval" - see _build_decision() below).
    # chain() below is what actually encodes "empty means empty."
    primary: str | None = None
    fallbacks: list[str] = field(default_factory=list)
    # M11 addition. Provider_keys classified PREMIUM for this capability,
    # in preference order - NOT part of chain()/attempted automatically.
    premium: list[str] = field(default_factory=list)
    # M-AIGW-1 addition. Provider_keys that WOULD have been in chain()/
    # premium after tier/AI_MODE partitioning, but were removed by
    # select()'s capability-filtering pass because they don't satisfy this
    # request's required capabilities - never populated by
    # _build_decision() itself (always [] there), only by select()'s own
    # post-processing. AIGateway.complete() reads this to distinguish
    # "nothing configured" (existing GatewayError) from "nothing
    # configured CAN do what this request needs"
    # (errors.NoCapableProviderError) - see that error's own docstring.
    capability_excluded: list[str] = field(default_factory=list)

    def chain(self) -> list[str]:
        """The full ordered, AUTO-ATTEMPTED sequence - primary, then each
        fallback in order (local + free tier only, post-M11). Never
        includes `premium` - AIGateway.complete() walks this list, never
        `primary`/`fallbacks` individually, and reads `premium` on its own
        only after this chain is exhausted. Returns [] when primary is
        None (M11's "nothing auto-attempted, ask before premium" case) -
        AIGateway.complete() already handles an empty chain by skipping
        straight to the premium-approval check, unchanged from how it
        already handled "chain exhausted with no response.\""""
        if self.primary is None:
            return []
        return [self.primary, *self.fallbacks]


# The configuration surface - a plain dict, not a database table, same
# "adding X is a code change" convention as PROVIDER_REGISTRY/
# REPLY_CLASSIFIER_REGISTRY elsewhere in this codebase. Must always
# contain a "default" entry - resolve() below falls back to it for any
# capability with no specific entry, so a newly-added capability never
# fails to route just because nobody has assigned it a policy yet.
#
# M11: this is now an ORDERED PREFERENCE LIST per capability - "try these
# provider_keys in this order," partitioned into auto-attempted (local/
# free) vs. approval-gated (premium) by app.ai_gateway.tiers.partition()
# and settings.AI_MODE inside select() below. "claude" stays first/only
# in the premium bucket for "default" - day-1 backward compatibility (see
# AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL's own docstring for how the actual
# approval ENFORCEMENT is what's new, not this list's shape).
#
# M-AIGW-3 (Gemini Free-Tier Split) adds "gemini_ai_studio" after "groq" -
# safe by construction: GOOGLE_AI_STUDIO_API_KEY is unset by default (see
# app.core.config.settings' own comment), so is_configured() is False and
# this new entry is silently skipped for every deployment until an
# operator sets it, same "additive, zero behavior change until configured"
# discipline as every other M11/M-AIGW addition to this file.
#
# Deliberately NOT adding plain "gemini" here in this same pass, disclosed
# rather than silently done either way: "gemini" has been registered and
# tiered PREMIUM since M11, but was NEVER actually part of this preference
# list - a deployment with GOOGLE_API_KEY configured has had a genuinely
# unreachable premium candidate this whole time. Adding it now would be a
# real, newly-ACTIVATED behavior change for any such deployment (a
# previously-dead GOOGLE_API_KEY would suddenly become live), which is a
# materially different risk than adding "gemini_ai_studio" (a brand new,
# certainly-unconfigured setting). Left as an explicit, easy, separate
# follow-up if plain "gemini" reachability via default routing is
# actually wanted.
CAPABILITY_PROVIDER_PREFERENCE: dict[str, list[str]] = {
    _DEFAULT_CAPABILITY_KEY: ["local_ollama", "groq", "gemini_ai_studio", "claude"],
}

# TEST-ONLY override seam, kept from M7.2 under its original name for
# minimal churn to existing tests (test_ai_execution_platform_e2e.py,
# test_supervisor_e2e.py, test_supervisor_invocation_action_e2e.py,
# test_research_analysis_agent_full_chain_e2e.py all inject a fake,
# deterministic RoutingDecision this way, exactly like `provider_lookup`
# is AIGateway's own test-only DI seam). Empty by default (unlike M7.2,
# where this dict WAS the real production routing table) - see
# ProviderRouter.select() below: a capability present here is returned
# VERBATIM, bypassing tier/AI_MODE resolution entirely, which is exactly
# what a test wants (a fixed, predictable chain regardless of settings).
# Production code must never write to this dict - only
# CAPABILITY_PROVIDER_PREFERENCE (and settings.AI_MODE) drive real routing.
ROUTING_POLICY: dict[str, RoutingDecision] = {}


def _build_decision(preference: list[str], ai_mode: str) -> RoutingDecision:
    local, free, premium = partition(preference)

    if ai_mode == "local_only":
        # Local tier ONLY - free-tier cloud providers are still a cloud
        # dependency, so they're deliberately excluded here, not folded in
        # with local the way hybrid mode folds them together.
        chain_candidates, premium_candidates = local, []
    elif ai_mode == "premium_only":
        chain_candidates, premium_candidates = premium, []
    elif ai_mode == "automatic_premium":
        chain_candidates, premium_candidates = [*local, *free, *premium], []
    else:  # "hybrid_recommended" (default) or any unrecognized value - the
        # safe fallback: never silently escalate further than documented.
        chain_candidates, premium_candidates = [*local, *free], premium

    # No special-casing needed for an empty chain_candidates - chain()
    # itself tolerates primary=None (returns []), and AIGateway.complete()
    # already handles "chain empty, check premium next" / "chain empty,
    # premium also empty -> clean GatewayError". This deliberately does
    # NOT fall back to attempting an unrelated tier (e.g. local_only with
    # no local candidate configured must NOT silently try a free/premium
    # provider - that would violate "never use cloud providers" for that
    # mode) - failing closed here is the correct, safe behavior.
    primary = chain_candidates[0] if chain_candidates else None
    fallbacks = chain_candidates[1:] if chain_candidates else []
    return RoutingDecision(primary=primary, fallbacks=fallbacks, premium=premium_candidates)


class ProviderRouter:
    @staticmethod
    def select(request: GatewayRequest) -> RoutingDecision:
        if request.capability in ROUTING_POLICY:
            # Test-only override - see ROUTING_POLICY's own docstring. A
            # capability present here bypasses tier/AI_MODE resolution
            # entirely BY DESIGN - capability-filtering (M-AIGW-1) is part
            # of that same bypassed resolution, so it's deliberately
            # skipped here too: a test wants a fixed, predictable chain
            # regardless of settings OR declared provider capabilities.
            return ROUTING_POLICY[request.capability]

        from app.core.config import settings  # lazy - see module docstring

        preference = CAPABILITY_PROVIDER_PREFERENCE.get(
            request.capability, CAPABILITY_PROVIDER_PREFERENCE[_DEFAULT_CAPABILITY_KEY]
        )
        decision = _build_decision(preference, settings.AI_MODE)

        required = derive_required_capabilities(request)
        if not required.any_required():
            # Fast path - see capabilities.filter_capable()'s own
            # docstring. Skips the PROVIDER_CLIENT_REGISTRY import entirely
            # for the common case (every existing caller today), not just
            # the filtering work - that import needs settings transitively
            # (every concrete provider client module imports
            # app.core.config.settings itself), which is exactly why it's
            # lazy and conditional, mirroring the `settings` import above.
            return decision

        from app.ai_gateway.providers.registry import PROVIDER_CLIENT_REGISTRY

        provider_level = {key: cls.capabilities for key, cls in PROVIDER_CLIENT_REGISTRY.items()}
        return _apply_capability_filter(decision, request, provider_level=provider_level)


def _apply_capability_filter(
    decision: RoutingDecision, request: GatewayRequest, *, provider_level: dict
) -> RoutingDecision:
    """M-AIGW-1 (Provider-Neutral AI Gateway foundation). Post-processes an
    already tier/AI_MODE-shaped RoutingDecision, dropping any provider_key
    that doesn't satisfy `request`'s required capabilities - see module
    docstring for why this lives here (in select(), as a distinct pass)
    rather than inside _build_decision() itself.

    Deliberately PURE - `provider_level` is an explicit parameter (a plain
    {provider_key: ProviderCapabilities} dict), never resolved by this
    function itself, exactly mirroring capabilities.filter_capable()'s own
    signature. select() is the only real caller, and the only place that
    does the (settings-requiring) PROVIDER_CLIENT_REGISTRY lookup to build
    that dict - see select()'s own comment. This function recomputes
    derive_required_capabilities() itself (cheap, and keeps this function
    correct/self-contained if ever called directly, e.g. from a test, with
    an empty provider_level and no real requirements)."""
    required = derive_required_capabilities(request)
    if not required.any_required():
        return decision

    capable_chain, excluded_chain = filter_capable(
        decision.chain(), required, model=request.model, provider_level=provider_level
    )
    capable_premium, excluded_premium = filter_capable(
        decision.premium, required, model=request.model, provider_level=provider_level
    )
    return RoutingDecision(
        primary=capable_chain[0] if capable_chain else None,
        fallbacks=capable_chain[1:] if capable_chain else [],
        premium=capable_premium,
        capability_excluded=excluded_chain + excluded_premium,
    )
