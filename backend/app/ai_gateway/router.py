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
"""
from dataclasses import dataclass, field

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
CAPABILITY_PROVIDER_PREFERENCE: dict[str, list[str]] = {
    _DEFAULT_CAPABILITY_KEY: ["local_ollama", "groq", "claude"],
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
            # Test-only override - see ROUTING_POLICY's own docstring.
            return ROUTING_POLICY[request.capability]

        from app.core.config import settings  # lazy - see module docstring

        preference = CAPABILITY_PROVIDER_PREFERENCE.get(
            request.capability, CAPABILITY_PROVIDER_PREFERENCE[_DEFAULT_CAPABILITY_KEY]
        )
        return _build_decision(preference, settings.AI_MODE)
