"""
AI pre-flight check - M11 (AI Provider Hierarchy). Lets the Research page ask
"will this run need premium approval?" BEFORE the user submits it, so the
Yes/No approval dialog (the spec's own UX) can be shown at submission time
rather than discovered mid-run.

Deliberate scope decision, disclosed rather than glossed over: this is a
PRE-FLIGHT check, not a true mid-workflow pause/resume. Research execution
is fully asynchronous (ResearchExecutionAction, via the M7 Workflow
Engine's worker) and AgentOutcome has no "paused, awaiting human input"
state (see app.ai_agents.base.AgentOutcome's own docstring - this
codebase's workflow/agent primitives were deliberately never built with
one). Building genuine mid-flight pause/resume would mean adding that
state across ResearchJobStatus, the Workflow Engine's step-runner, and the
Live Workflow Progress UI - a materially larger, separate architectural
change (see docs/architecture/m11-ai-provider-hierarchy-plan.md Section 5,
"Phase 2"). This module intentionally covers the common, expected case
(the user is prompted before submitting, exactly like the spec's own
mockup shows) - if a job's approval need somehow changes between preflight
and actual execution (a local/free provider that was up during preflight
goes down mid-run, for instance), the run simply degrades to the existing
"AI analysis failed"-shaped outcome (see llm_engine.py's
_premium_approval_outcomes()), with a clear message to re-run once
approved - never a silent crash, never a silent premium call.
"""
from app.ai_gateway.confidence import assess_complexity
from app.ai_gateway.request import GatewayRequest
from app.ai_gateway.router import ProviderRouter
from app.core.config import settings
from app.research.analysis.llm_agent import RESEARCH_ANALYSIS_AGENT_KEY, RESPONSE_FORMAT
from app.schemas.research_request import AIPreflightResult


def _is_configured(provider_key: str) -> bool:
    from app.ai_gateway.providers.registry import get_provider_client

    try:
        return get_provider_client(provider_key).is_configured()
    except KeyError:
        return False


def compute_ai_preflight(*, prompt_char_length: int = 0, document_count: int = 0) -> AIPreflightResult:
    if settings.RESEARCH_ANALYSIS_ENGINE_BACKEND != "llm":
        return AIPreflightResult(applicable=False, approval_required=False)

    request = GatewayRequest(capability=RESEARCH_ANALYSIS_AGENT_KEY, response_format=RESPONSE_FORMAT)
    decision = ProviderRouter.select(request)

    chain_has_configured_candidate = any(_is_configured(key) for key in decision.chain())
    if chain_has_configured_candidate or not decision.premium:
        # Local/free will be attempted automatically and at least one
        # candidate is actually usable (or there's no premium tier to ask
        # about at all, e.g. automatic_premium/premium_only modes) - no
        # approval needed.
        return AIPreflightResult(applicable=True, approval_required=False)

    if not settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL:
        return AIPreflightResult(applicable=True, approval_required=False)

    from app.ai_gateway.accounting import estimate_pre_call_cost_usd

    candidate = decision.premium[0]
    assessment = assess_complexity(
        context_char_length=prompt_char_length,
        document_count=document_count,
        response_format=RESPONSE_FORMAT,
    )
    estimated_cost_usd = estimate_pre_call_cost_usd(
        provider_key=candidate,
        model=_default_model_for(candidate),
        prompt_char_length=prompt_char_length,
    )
    return AIPreflightResult(
        applicable=True,
        approval_required=True,
        candidate_provider_key=candidate,
        estimated_cost_usd=estimated_cost_usd,
        reasons=assessment.reasons,
    )


def _default_model_for(provider_key: str) -> str:
    """Best-effort model id for the pre-call cost estimate only - the real
    call (if approved) resolves its own model from ExecutionPolicy/
    settings exactly as today; this is purely cosmetic for the estimate
    lookup in accounting.py's price table."""
    return {
        "claude": settings.ANTHROPIC_DEFAULT_MODEL,
        "openai": settings.OPENAI_DEFAULT_MODEL,
        "gemini": settings.GOOGLE_DEFAULT_MODEL,
    }.get(provider_key) or provider_key
