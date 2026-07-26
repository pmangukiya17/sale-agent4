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

M-AIGW-1 (Provider-Neutral AI Gateway foundation) additions:

  - `complete()`'s "chain and premium both empty" branch now distinguishes
    two failure classes: ordinary "nothing configured"
    (unchanged GatewayError) vs. `decision.capability_excluded` being
    non-empty, meaning ProviderRouter.select() DID find configured
    candidates but none of them declare the capabilities this request
    needs - raises the new, distinct `NoCapableProviderError` instead (see
    errors.py's own docstring for why these are kept separate).
  - `_raise_premium_approval_required()` now reads `request.document_count`
    (previously hardcoded to 0 regardless of the real request - see this
    module's own git history) and `request.requires_deep_reasoning`
    (previously never read at all, defaulting confidence.assess_complexity's
    `reasoning_depth_hint` to "shallow" unconditionally) - both real signal
    that was already flowing into `GatewayRequest` but never reaching this
    call site.
  - `preflight()` - the Gateway's own public "would this need approval,
    and what would it cost" answer (see request.PreflightResult's own
    docstring for why this replaces app.research.ai_preflight's four
    separate direct calls into Gateway internals).
"""
import logging
import time

from app.ai_gateway.accounting import estimate_pre_call_cost_usd
from app.ai_gateway.confidence import assess_complexity
from app.ai_gateway.errors import GatewayError, NoCapableProviderError, PremiumApprovalRequiredError
from app.ai_gateway.request import GatewayRequest, GatewayResponse, GatewayStreamChunk, PreflightResult
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
                            company_profile_id=request.company_profile_id,
                            user_id=request.user_id,
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
                        company_profile_id=request.company_profile_id,
                        user_id=request.user_id,
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
            document_count=request.document_count,
            response_format=request.response_format,
            reasoning_depth_hint="deep" if request.requires_deep_reasoning else "shallow",
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
                company_profile_id=request.company_profile_id,
                user_id=request.user_id,
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
        if decision.capability_excluded:
            logger.info(
                "ai_gateway.capability_excluded",
                extra={"capability": request.capability, "excluded_provider_keys": decision.capability_excluded},
            )
        chain = decision.chain()
        if not chain and not decision.premium:
            if decision.capability_excluded:
                raise NoCapableProviderError(
                    f"No configured provider for capability '{request.capability}' supports the "
                    f"capabilities this request requires (excluded: {decision.capability_excluded})",
                    excluded_provider_keys=decision.capability_excluded,
                )
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

    def preflight(self, request: GatewayRequest, *, prompt_char_length: int = 0) -> PreflightResult:
        """M-AIGW-1 (Provider-Neutral AI Gateway foundation). Answers "would
        completing THIS request right now need premium approval, and if so
        what would it cost and why" WITHOUT attempting a real call - reads
        only `is_configured()` (no network call - see
        providers.base.ProviderClient's own docstring) plus the same
        confidence/cost-estimate machinery `_raise_premium_approval_required()`
        uses for the in-flight case.

        `prompt_char_length` is a separate parameter, not derived from
        `request.messages`, because a genuine pre-submission preflight check
        (the only caller today - app.research.ai_preflight) is called
        BEFORE PromptBuilder.build() has ever run for this request - there
        are no real messages yet, only a caller-supplied estimate (e.g.
        summed length of not-yet-analyzed raw documents). `request.document_count`
        IS read directly from the request - unlike prompt_char_length, a
        real document count is already known pre-submission and is exactly
        the same field `_raise_premium_approval_required()` reads for the
        in-flight case, unifying what were previously two independently-
        threaded document counts into one.

        Deliberately does NOT reuse ProviderRouter.select()'s capability-
        filtering result to change the approval answer itself this pass -
        if every capable candidate is also unconfigured, this still reports
        "needs approval" against the (possibly capability-filtered) premium
        list exactly as select() resolved it; a request capability-excluded
        down to nothing configured at all is a `NoCapableProviderError`
        only inside complete() itself (see that method), not surfaced as a
        distinct PreflightResult shape - out of scope for this pass, noted
        here rather than silently glossed over.
        """
        decision = ProviderRouter.select(request)
        chain_has_configured_candidate = any(self._is_configured_safe(key) for key in decision.chain())
        if chain_has_configured_candidate or not decision.premium:
            return PreflightResult(approval_required=False)

        if not settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL:
            return PreflightResult(approval_required=False)

        candidate = decision.premium[0]
        model = request.model or self._default_model_safe(candidate) or candidate
        estimated_cost_usd = estimate_pre_call_cost_usd(
            provider_key=candidate,
            model=model,
            prompt_char_length=prompt_char_length,
            expected_completion_tokens=request.max_tokens or 1024,
        )
        assessment = assess_complexity(
            context_char_length=prompt_char_length,
            document_count=request.document_count,
            response_format=request.response_format,
            reasoning_depth_hint="deep" if request.requires_deep_reasoning else "shallow",
        )
        return PreflightResult(
            approval_required=True,
            candidate_provider_key=candidate,
            estimated_cost_usd=estimated_cost_usd,
            reasons=assessment.reasons,
        )

    def _is_configured_safe(self, provider_key: str) -> bool:
        try:
            return self._resolve_provider(provider_key).is_configured()
        except KeyError:
            return False

    def _default_model_safe(self, provider_key: str) -> str | None:
        try:
            return self._resolve_provider(provider_key).default_model
        except KeyError:
            return None

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
