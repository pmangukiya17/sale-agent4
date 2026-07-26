"""
Normalized error hierarchy for the AI Gateway - M7.2. Every concrete
ProviderClient.complete() implementation MUST catch its own SDK's
exceptions and re-raise one of these before anything leaves
app/ai_gateway/providers/ - exactly the same normalization discipline
app.workflow_engine.actions.base.ActionOutcome already applies one layer
up (a deliberately small, stable vocabulary the rest of the system reads
generically, never a provider-specific exception type).

Two independent properties per error TYPE (not decided per-instance),
both read generically by AIGateway's own retry/fallback loop (client.py)
- it never branches on which concrete GatewayError subclass it caught
beyond these two flags:

  retryable - worth immediately retrying the SAME provider (bounded by
  AI_GATEWAY_MAX_ATTEMPTS_PER_PROVIDER)? True for transient/provider-side
  failures; False for anything that would fail identically on a retry.

  fallback_eligible - worth trying the NEXT provider in the routing
  chain once retries on this one are exhausted? True unless the failure
  is a property of the REQUEST itself (a malformed request tends to be
  rejected by every provider for the same underlying reason, so falling
  through wastes a call without a real chance of success).
"""


class GatewayError(Exception):
    """Base class for every normalized AI Gateway error. Never raised
    directly - always one of the subclasses below."""

    retryable: bool = False
    fallback_eligible: bool = False

    def __init__(self, message: str, *, provider_key: str | None = None):
        super().__init__(message)
        self.provider_key = provider_key


class ProviderTimeoutError(GatewayError):
    """The request exceeded AI_GATEWAY_DEFAULT_TIMEOUT_SECONDS (or a
    per-request override)."""

    retryable = True
    fallback_eligible = True


class ProviderRateLimitError(GatewayError):
    """The provider's own rate limit was hit (HTTP 429 or equivalent)."""

    retryable = True
    fallback_eligible = True


class ProviderUnavailableError(GatewayError):
    """A transient provider-side failure (5xx, connection reset, etc.)."""

    retryable = True
    fallback_eligible = True


class ProviderAuthError(GatewayError):
    """Bad/missing API key, or the account isn't entitled to the
    requested model - never worth retrying THIS provider (retrying with
    the same credentials cannot succeed), but still worth falling
    through to a DIFFERENT provider, since that failure mode is specific
    to this one provider's credentials."""

    retryable = False
    fallback_eligible = True


class InvalidRequestError(GatewayError):
    """The request itself was malformed for this provider (e.g. an
    unsupported response_format/tool shape) - not retryable, and NOT a
    good fallback candidate either, since a different provider is likely
    to reject the same underlying request for the same reason."""

    retryable = False
    fallback_eligible = False


class InvalidResponseError(GatewayError):
    """The provider returned a response this Gateway could not parse
    into a GatewayResponse (e.g. malformed JSON when response_format
    requested structured output) - not worth retrying the same provider
    (the same input tends to produce the same malformed output), but IS
    worth falling through to a different provider/model."""

    retryable = False
    fallback_eligible = True


class BudgetExceededError(GatewayError):
    """Reserved for a future milestone's hard budget enforcement (see
    client.py's own docstring for why M7.2 only logs a soft overage
    against ExecutionPolicy.budget_usd) - not raised anywhere in M7.2."""

    retryable = False
    fallback_eligible = False


class PremiumApprovalRequiredError(GatewayError):
    """M11 (AI Provider Hierarchy). Raised by AIGateway.complete() when the
    local/free tier chain is exhausted (every candidate unconfigured or
    failed), a premium-tier provider exists in the routing decision, and
    settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL is True, and the request
    was not already marked premium_approved=True. This is NOT a failure in
    the ordinary sense - it's the Gateway's "STOP, ask the user" decision
    point (see the AI Provider Hierarchy spec's own AI REQUEST FLOW) -
    still modeled as a GatewayError subclass so it flows through the exact
    same normalized-error plumbing every caller already handles, but
    neither retryable nor fallback_eligible (there is nothing further to
    try automatically; a human decision is required).

    Carries the data a caller needs to render the approval prompt without
    re-deriving it: `estimated_cost_usd` (see
    accounting.estimate_pre_call_cost_usd - a heuristic, pre-call estimate,
    since real token counts don't exist until after a call),
    `reasons` (from app.ai_gateway.confidence.assess_complexity), and
    `candidate_provider_key` (which premium provider would be attempted if
    approved). See app.ai_agents.runtime.AgentRuntime.run_with_metadata()
    for the one place this is caught specifically (narrower than the
    generic GatewayError catch) so this structured data isn't lost."""

    retryable = False
    fallback_eligible = False

    def __init__(
        self,
        message: str,
        *,
        provider_key: str | None = None,
        candidate_provider_key: str,
        estimated_cost_usd: float | None = None,
        reasons: list[str] | None = None,
    ):
        super().__init__(message, provider_key=provider_key)
        self.candidate_provider_key = candidate_provider_key
        self.estimated_cost_usd = estimated_cost_usd
        self.reasons = reasons or []
