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

M-AIGW-1 (Provider-Neutral AI Gateway foundation) rewrite: this module
used to call ProviderRouter.select(), providers.registry.get_provider_client(),
confidence.assess_complexity(), and accounting.estimate_pre_call_cost_usd()
directly, plus carried its own hardcoded provider_key -> default-model
dict (`_default_model_for`, covering exactly "claude"/"openai"/"gemini" -
silently wrong for any provider outside that list). All four Gateway-
internal calls, and the hardcoded dict, are gone - this is now a thin
caller of the Gateway's own public `AIGateway.preflight()` (see
app.ai_gateway.client's and app.ai_gateway.request.PreflightResult's own
docstrings), reading `default_model` off whichever ProviderClient the
Gateway resolves internally instead of guessing from a name string. The
ONE thing that stays here, correctly - `RESEARCH_ANALYSIS_ENGINE_BACKEND
!= "llm"` -> `applicable=False` - is a Research-domain concept (which
analysis engine Research itself is configured to use), not a Gateway
concept; the Gateway has no notion of "applicable" at all (see
PreflightResult's own docstring).
"""
from app.ai_gateway.client import AIGateway
from app.ai_gateway.request import GatewayRequest
from app.core.config import settings
from app.research.analysis.llm_agent import RESEARCH_ANALYSIS_AGENT_KEY, RESPONSE_FORMAT
from app.schemas.research_request import AIPreflightResult


def compute_ai_preflight(*, prompt_char_length: int = 0, document_count: int = 0) -> AIPreflightResult:
    if settings.RESEARCH_ANALYSIS_ENGINE_BACKEND != "llm":
        return AIPreflightResult(applicable=False, approval_required=False)

    request = GatewayRequest(
        capability=RESEARCH_ANALYSIS_AGENT_KEY,
        response_format=RESPONSE_FORMAT,
        document_count=document_count,
    )
    result = AIGateway().preflight(request, prompt_char_length=prompt_char_length)
    return AIPreflightResult(
        applicable=True,
        approval_required=result.approval_required,
        candidate_provider_key=result.candidate_provider_key,
        estimated_cost_usd=result.estimated_cost_usd,
        reasons=result.reasons,
    )
