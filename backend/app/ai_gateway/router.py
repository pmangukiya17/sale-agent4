"""
Provider Router - M7.2. Decides WHICH provider (and, if it fails, which
to fall back to) serves a given GatewayRequest, keyed by
`request.capability` - never by agent_key, and never known by anything
above the AI Gateway (the approved architecture's own "the rest of the
system should never know which provider was selected"). Deliberately a
thin, swappable policy - see ROUTING_POLICY's own comment for why this
is a plain Python dict rather than a database table.

Day one: every capability maps to one default provider with no fallback
chain, exactly as specified. Nothing about ProviderRouter.select()'s own
signature needs to change as the policy grows richer (cost-based,
load-based, per-company overrides, A/B testing between providers) - only
the data/logic inside select() does.
"""
from dataclasses import dataclass, field

from app.ai_gateway.request import GatewayRequest

_DEFAULT_CAPABILITY_KEY = "default"


@dataclass(frozen=True)
class RoutingDecision:
    primary: str
    fallbacks: list[str] = field(default_factory=list)

    def chain(self) -> list[str]:
        """The full ordered attempt sequence - primary, then each
        fallback in order. AIGateway.complete() walks this list, never
        `primary`/`fallbacks` individually."""
        return [self.primary, *self.fallbacks]


# The configuration surface - a plain dict, not a database table, same
# "adding X is a code change" convention as PROVIDER_REGISTRY/
# REPLY_CLASSIFIER_REGISTRY elsewhere in this codebase. Must always
# contain a "default" entry - resolve() below falls back to it for any
# capability with no specific entry, so a newly-added capability never
# fails to route just because nobody has assigned it a policy yet.
#
# Day-1 state: every entry (including "default") points at the same
# single provider, with no fallback chain - deliberately matching "it
# may simply return a default provider" from the approved architecture.
# The provider_key strings below must match a key registered in
# app.ai_gateway.providers.registry.PROVIDER_CLIENT_REGISTRY.
ROUTING_POLICY: dict[str, RoutingDecision] = {
    _DEFAULT_CAPABILITY_KEY: RoutingDecision(primary="claude"),
}


class ProviderRouter:
    @staticmethod
    def select(request: GatewayRequest) -> RoutingDecision:
        return ROUTING_POLICY.get(request.capability, ROUTING_POLICY[_DEFAULT_CAPABILITY_KEY])
