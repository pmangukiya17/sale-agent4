"""
ProviderClient - the contract every concrete provider adapter
implements - M7.2. One method that does real work (`complete`), one that
never touches the network (`is_configured`) - mirrors
app.delivery.providers.base's own ChannelProvider shape (that precedent
already established "is_configured() as a cheap, no-network readiness
check" in this codebase; M7.2 reuses it rather than inventing a new
one).

M-AIGW-1 additions (Provider-Neutral AI Gateway foundation - see
docs/architecture/provider-neutral-ai-gateway-plan.md):

  - `capabilities: ClassVar[ProviderCapabilities]` - each concrete client
    declares what its wire-format/SDK integration can actually do,
    protocol-level (see app.ai_gateway.capabilities' own docstring for why
    this is provider-level, not per-model, and for the separate
    per-(provider, model) override table that covers the fields that DO
    vary per model). Read by ProviderRouter.select() to filter routing
    candidates by what a request actually needs, never by provider
    identity - the whole point of this addition.
  - `default_model` property - each client's own best-effort default
    model id (typically `settings.<PROVIDER>_DEFAULT_MODEL`), exposed
    uniformly so no caller outside this package ever needs its own
    hardcoded provider_key -> model dict again (this replaced
    app.research.ai_preflight's own such dict, which is exactly the kind
    of Research-knows-provider-identity coupling this milestone closes).
    May return None if nothing is configured - callers must handle that,
    never assume a real value.

    Deliberately NOT `@abstractmethod` (unlike `complete`/`is_configured`)
    - it has a concrete `None` default on this base class instead. Several
    existing test-only fake ProviderClient subclasses across this
    project's e2e test suites (test_ai_execution_platform_e2e.py,
    test_ai_provider_hierarchy_e2e.py, test_supervisor_e2e.py,
    test_supervisor_invocation_action_e2e.py,
    test_research_analysis_agent_full_chain_e2e.py) predate this addition
    and only implement `key`/`is_configured`/`complete` - making this a
    true abstractmethod would make every one of those fakes fail to
    instantiate (TypeError: Can't instantiate abstract class), a real
    backward-compatibility break this milestone must not introduce. Every
    real provider client still overrides this with its own concrete
    implementation (see each one's own `default_model` property) - the
    `None` base default only ever matters for a fake/test subclass that
    doesn't care about it.
"""
from abc import ABC, abstractmethod
from typing import ClassVar

from app.ai_gateway.capabilities import ProviderCapabilities
from app.ai_gateway.request import GatewayRequest, GatewayResponse


class ProviderClient(ABC):
    key: ClassVar[str]
    capabilities: ClassVar[ProviderCapabilities] = ProviderCapabilities()

    @abstractmethod
    def complete(self, request: GatewayRequest) -> GatewayResponse:
        """Must raise one of app.ai_gateway.errors' normalized
        GatewayError subclasses for every failure mode - never let a
        provider SDK's own exception type escape this method."""
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        """True only if this provider has everything it needs (API key
        at minimum) to attempt a real call - never makes a network call
        itself. AIGateway.complete() checks this before attempting a
        provider in the routing chain, so a genuinely unconfigured
        provider fails fast with a clear ProviderAuthError-shaped
        message instead of an opaque SDK-level exception."""
        raise NotImplementedError

    @property
    def default_model(self) -> str | None:
        """This client's own configured default model id, or None if
        unconfigured/not overridden - never a hardcoded literal, never
        guessed. Every real concrete client overrides this (computing the
        same value it already uses internally in `complete()`, e.g.
        `settings.ANTHROPIC_DEFAULT_MODEL`); this property exposes that
        same value for callers (e.g. AIGateway.preflight()) that need a
        best-effort model id before actually attempting a call. See this
        class's own docstring for why the base default is a concrete
        `None`, not `@abstractmethod`."""
        return None
