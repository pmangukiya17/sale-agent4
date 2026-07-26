"""
AIGateway - M7.2, extended M11 (AI Provider Hierarchy). The single entry
point everything above app/ai_gateway/ calls (PromptBuilder, via
AgentRuntime - see app.ai_agents.runtime). Owns the one piece of behavior
nothing else in this layer is allowed to own: walking a RoutingDecision's
provider chain, retrying a transient failure on the current provider up to
settings.AI_GATEWAY_MAX_ATTEMPTS_PER_PROVIDER times, and falling through
to the next provider in the chain when a fallback-eligible error persists
- reading only the two generic GatewayError flags (`retryable`,
`fallback_eligible`), never branching on a specific error subclass or
provider identity.

M11 addition - the "STOP, ask user" gate: RoutingDecision now carries a
separate `premium` list (see router.py) that is NEVER included in
`chain()` and is therefore never auto-attempted by the loop above. Once
`chain()` is exhausted, if `decision.premium` is non-empty, this method
checks settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL and
request.premium_approved:
  - gate disabled, OR request already approved -> attempt the premium
    list with the exact same walk logic as the main chain (so a
    previously-approved or gate-disabled call behaves identically to
    M7.2's single-chain behavior - this is what keeps every existing
    deployment with only "claude" configured working unchanged when the
    gate is off).
  - gate enabled AND not yet approved -> raise
    PremiumApprovalRequiredError with a pre-call cost estimate
    (accounting.estimate_pre_call_cost_usd) and confidence-derived reasons
    (confidence.assess_complexity) instead of calling the premium
    provider - the caller (ultimately a human, via the approval UI) must
    decide, then re-call with premium_approved=True.

Cost accounting is computed by each ProviderClient itself, via
app.ai_gateway.accounting.build_usage() (see claude_client.py/
openai_client.py/gemini_client.py/openai_compatible_client.py - every
GatewayResponse.usage.cost_usd already arrives populated, or None for an
unpriced model). This module only READS that value, to check it against
GatewayRequest.budget_usd. That check is deliberately SOFT: a request
whose estimated cost exceeds its budget is still sent, with the overage
merely available for the caller to notice via the returned
TokenUsage.cost_usd. Hard pre-flight budget rejection (raising
BudgetExceededError before a call is even attempted) is real, meaningful
future work - it needs a per-company/per-period spend total to check
against, which does not exist yet.

`stream()` raises NotImplementedError - unchanged from M7.2, see
request.py's own GatewayStreamChunk docstring.

`provider_lookup` (constructor param) is a deliberate testability seam,
not just an incidental DI convenience - unchanged from M7.2, see that
milestone's own docstring reasoning (still applies verbatim to the two new
M11 provider clients, both lazily imported the same way via the real
registry).
"""
import logging
import time

from app.ai_gateway.accounting import estimate_pre_call_cost_usd
from app.ai_gateway.confidence import assess_complexity
from app.ai_gateway.errors import GatewayError, PremiumApprovalRequiredError
from app.ai_gateway.request import GatewayRequest, GatewayResponse, GatewayStreamChunk
from app.ai_gateway.request_log import AIRequestLogEntry, log_ai_request
from app.ai_gateway.router import ProviderRouter, RoutingDecision
from app.ai_gateway.tiers import tier_of
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

    def _walk(self, request: GatewayRequest, provider_keys: list[str]) -> tuple[GatewayResponse | None, GatewayError | None]:
        """Shared walk logic for both the auto-attempted chain and (once
        approved/ungated) the premium list - identical semantics to M7.2's
        single inline loop, just reusable over either list. Returns
        (response, None) on success, or (None, last_error) if every
        candidate was exhausted without raising (the caller decides what
        to do next); raises directly, same as before, the moment a
        non-fallback-eligible error is hit."""
        last_error: GatewayError | None = None

        for provider_key in provider_keys:
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
            started_at = time.monotonic()
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
                    log_ai_request(
                        AIRequestLogEntry(
                            capability=request.capability,
                            provider_key=response.provider_key,
                            model=response.model,
                            tier=tier_of(provider_key).value,
                            duration_ms=(time.monotonic() - started_at) * 1000,
                            prompt_tokens=response.usage.prompt_tokens,
                            completion_tokens=response.usage.completion_tokens,
                            cost_usd=response.usage.cost_usd,
                            success=True,
                        )
                    )
                    return response, None

            if last_error is not None and not last_error.fallback_eligible:
                log_ai_request(
                    AIRequestLogEntry(
                        capability=request.capability,
                        provider_key=provider_key,
                        model=request.model,
                        tier=tier_of(provider_key).value,
                        duration_ms=(time.monotonic() - started_at) * 1000,
                        prompt_tokens=None,
                        completion_tokens=None,
                        cost_usd=None,
                        success=False,
                        error_type=type(last_error).__name__,
                    )
                )
                raise last_error

        return None, last_error

    def _raise_premium_approval_required(self, request: GatewayRequest, decision: RoutingDecision) -> None:
        candidate = decision.premium[0]
        model = request.model or candidate
        prompt_char_length = sum(len(m.get("content", "")) for m in request.messages)
        estimated_cost_usd = estimate_pre_call_cost_usd(
            provider_key=candidate,
            model=model,
            prompt_char_length=prompt_char_length,
            expected_completion_tokens=request.max_tokens or 1024,
        )
        assessment = assess_complexity(
            context_char_length=prompt_char_length,
            document_count=0,
            response_format=request.response_format,
        )
        log_ai_request(
            AIRequestLogEntry(
                capability=request.capability,
                provider_key=None,
                model=model,
                tier="premium",
                duration_ms=0.0,
                prompt_tokens=None,
                completion_tokens=None,
                cost_usd=estimated_cost_usd,
                success=False,
                confidence_score=assessment.score,
                error_type="PremiumApprovalRequiredError",
            )
        )
        raise PremiumApprovalRequiredError(
            f"Local/free providers exhausted for capability '{request.capability}'; "
            f"premium provider '{candidate}' requires explicit user approval before use.",
            candidate_provider_key=candidate,
            estimated_cost_usd=estimated_cost_usd,
            reasons=assessment.reasons,
        )

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        decision = ProviderRouter.select(request)
        chain = decision.chain()
        if not chain and not decision.premium:
            raise GatewayError(f"No provider chain resolved for capability '{request.capability}'")

        response, last_error = (None, None)
        if chain:
            response, last_error = self._walk(request, chain)
            if response is not None:
                return response

        if not decision.premium:
            if last_error is not None:
                raise last_error
            raise GatewayError(f"No provider in the chain for capability '{request.capability}' could be attempted")

        # Local/free tier exhausted (or never applicable, e.g. premium_only
        # mode already folded premium into `chain` and returned above) -
        # decision.premium is only ever non-empty here for
        # hybrid_recommended, where escalation requires approval.
        if not request.premium_approved and settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL:
            self._raise_premium_approval_required(request, decision)

        response, last_error = self._walk(request, decision.premium)
        if response is not None:
            return response
        if last_error is not None:
            raise last_error
        raise GatewayError(f"No premium provider for capability '{request.capability}' could be attempted")

    def stream(self, request: GatewayRequest):  # -> Iterator[GatewayStreamChunk]
        raise NotImplementedError(
            "AIGateway.stream() is reserved for a future milestone - GatewayStreamChunk's shape is "
            "already fixed in app.ai_gateway.request so no caller-facing change is needed when it "
            "ships. M7.2/M11 implement complete() only."
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
