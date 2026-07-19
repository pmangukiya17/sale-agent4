"""
AIGateway - M7.2. The single entry point everything above app/ai_gateway/
calls (PromptBuilder, via AgentRuntime - see app.ai_agents.runtime).
Owns the one piece of behavior nothing else in this layer is allowed to
own: walking a RoutingDecision's provider chain, retrying a transient
failure on the current provider up to
settings.AI_GATEWAY_MAX_ATTEMPTS_PER_PROVIDER times, and falling through
to the next provider in the chain when a fallback-eligible error persists
- reading only the two generic GatewayError flags (`retryable`,
`fallback_eligible`), never branching on a specific error subclass or
provider identity.

Cost accounting is computed by each ProviderClient itself, via
app.ai_gateway.accounting.build_usage() (see claude_client.py/
openai_client.py/gemini_client.py - every GatewayResponse.usage.cost_usd
already arrives populated, or None for an unpriced model). This module
only READS that value, to check it against GatewayRequest.budget_usd.
That check is deliberately SOFT in M7.2: a
request whose estimated cost exceeds its budget is still sent, with the
overage merely available for the caller to notice via the returned
TokenUsage.cost_usd. Hard pre-flight budget rejection (raising
BudgetExceededError before a call is even attempted) is real, meaningful
future work - it needs a per-company/per-period spend total to check
against, which does not exist yet in M7.2's scope (no new DB table was
approved for this milestone). Building a hard budget gate against
nothing but a single request's own estimated cost, with no running total
to compare it to, would be a fake guarantee, not a real one - so M7.2
intentionally ships the honest, weaker version.

`stream()` raises NotImplementedError. Real token-by-token streaming
needs a genuinely different per-provider code path (SSE/chunk iteration)
in every ProviderClient, none of which exists yet - declaring the method
now (with GatewayStreamChunk's shape already fixed in request.py) means
nothing above this layer needs to change when streaming is actually
implemented in a future milestone; only this method's body does.

`provider_lookup` (constructor param) is a deliberate testability seam,
not just an incidental DI convenience. app.ai_gateway.providers.registry
imports the three concrete provider client modules at module level,
which in turn `import anthropic`/`import openai`/`from google import
genai` - real third-party SDKs this project cannot install in every
environment (e.g. this sandbox has none of the three installed). If
AIGateway imported that registry at MODULE level, merely importing
app.ai_gateway.client - let alone constructing an AIGateway() - would
fail wherever those SDKs aren't present, which would make this class
untestable without them. Instead, the real registry is imported lazily,
inside _resolve_provider(), only at the moment complete() actually needs
to look a provider up - the exact same "unset until configured, fails
only at first real use" discipline already established by
CREDENTIAL_ENCRYPTION_KEY and ensure_builtin_actions_registered(). Tests
that need to run without the real SDKs installed (see
tests/test_ai_execution_platform_e2e.py) pass their own `provider_lookup`
callable and never touch the real registry or its imports at all.
"""
import logging

from app.ai_gateway.errors import GatewayError
from app.ai_gateway.request import GatewayRequest, GatewayResponse, GatewayStreamChunk
from app.ai_gateway.router import ProviderRouter
from app.core.config import settings

logger = logging.getLogger(__name__)


class AIGateway:
    def __init__(self, provider_lookup=None):
        self._provider_lookup = provider_lookup

    def _resolve_provider(self, provider_key: str):
        if self._provider_lookup is not None:
            return self._provider_lookup(provider_key)
        from app.ai_gateway.providers.registry import get_provider_client

        return get_provider_client(provider_key)

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        decision = ProviderRouter.select(request)
        chain = decision.chain()
        if not chain:
            raise GatewayError(f"No provider chain resolved for capability '{request.capability}'")

        last_error: GatewayError | None = None

        for provider_key in chain:
            try:
                provider = self._resolve_provider(provider_key)
            except KeyError as exc:
                logger.error("ai_gateway.unknown_provider_in_chain", extra={"provider_key": provider_key})
                last_error = GatewayError(str(exc))
                continue

            if not provider.is_configured():
                logger.warning("ai_gateway.provider_not_configured", extra={"provider_key": provider_key})
                last_error = GatewayError(f"Provider '{provider_key}' is not configured", provider_key=provider_key)
                continue

            attempt = 0
            while attempt < settings.AI_GATEWAY_MAX_ATTEMPTS_PER_PROVIDER:
                attempt += 1
                try:
                    response = provider.complete(request)
                except GatewayError as exc:
                    last_error = exc
                    logger.warning(
                        "ai_gateway.provider_call_failed",
                        extra={
                            "provider_key": provider_key,
                            "attempt": attempt,
                            "error_type": type(exc).__name__,
                            "retryable": exc.retryable,
                            "fallback_eligible": exc.fallback_eligible,
                        },
                    )
                    if exc.retryable and attempt < settings.AI_GATEWAY_MAX_ATTEMPTS_PER_PROVIDER:
                        continue
                    break
                else:
                    self._check_soft_budget(request, response)
                    return response

            if last_error is not None and not last_error.fallback_eligible:
                raise last_error

        if last_error is not None:
            raise last_error
        raise GatewayError(f"No provider in the chain for capability '{request.capability}' could be attempted")

    def stream(self, request: GatewayRequest):  # -> Iterator[GatewayStreamChunk]
        raise NotImplementedError(
            "AIGateway.stream() is reserved for a future milestone - GatewayStreamChunk's shape is "
            "already fixed in app.ai_gateway.request so no caller-facing change is needed when it "
            "ships. M7.2 implements complete() only."
        )

    @staticmethod
    def _check_soft_budget(request: GatewayRequest, response: GatewayResponse) -> None:
        if request.budget_usd is None or response.usage.cost_usd is None:
            return
        if response.usage.cost_usd > request.budget_usd:
            logger.warning(
                "ai_gateway.soft_budget_exceeded",
                extra={
                    "capability": request.capability,
                    "budget_usd": request.budget_usd,
                    "actual_cost_usd": response.usage.cost_usd,
                    "provider_key": response.provider_key,
                },
            )
