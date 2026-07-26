"""
AI request logging - M11 (AI Provider Hierarchy). Structured-logs every
attempted AI Gateway call (timestamp - implicit in every log record via
the standard `logging` module, provider, model, tier, capability,
duration, tokens, cost, success/failure, confidence score, and - since
GatewayRequest.company_profile_id/user_id were threaded through from the
caller - workspace/user context) via the standard `logging` module - the
same observability discipline every other point in app.ai_gateway.client
already uses (ai_gateway.provider_call_failed, ai_gateway.soft_budget_exceeded,
etc.), extended into one purpose-built record shape instead of ad-hoc
`extra=` dicts scattered per call site.

`company_profile_id` is this codebase's honest analog to the spec's
"Workspace" field - no separate workspace/multi-user concept exists yet
(see docs/architecture/m11-ai-provider-hierarchy-plan.md Section 3.3);
both fields are optional and only populated for capabilities that have
actually threaded that context down to a GatewayRequest so far (Research,
via LLMAnalysisEngine - see that module's own docstring) - every other
capability logs with these as None until it does the same, no capability
is required to populate them.

Deliberately NOT a new database table this phase - mirrors
accounting.py's own stated reasoning ("no cost dashboard exists yet");
persisting this into a queryable table is real, clean future work once an
actual analytics view is wanted, not a blocker to shipping the routing/
policy mechanism itself. A future migration can add an ai_request_logs
table and swap log_ai_request()'s body to also INSERT a row - callers of
this function never need to change.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger("app.ai_gateway.request_log")


@dataclass(frozen=True)
class AIRequestLogEntry:
    capability: str
    provider_key: str | None
    model: str | None
    tier: str | None
    duration_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: float | None
    success: bool
    confidence_score: float | None = None
    error_type: str | None = None
    company_profile_id: str | None = None
    user_id: str | None = None


def log_ai_request(entry: AIRequestLogEntry) -> None:
    logger.info(
        "ai_gateway.request_completed" if entry.success else "ai_gateway.request_failed",
        extra={
            "capability": entry.capability,
            "provider_key": entry.provider_key,
            "model": entry.model,
            "tier": entry.tier,
            "duration_ms": entry.duration_ms,
            "prompt_tokens": entry.prompt_tokens,
            "completion_tokens": entry.completion_tokens,
            "cost_usd": entry.cost_usd,
            "confidence_score": entry.confidence_score,
            "error_type": entry.error_type,
            "company_profile_id": entry.company_profile_id,
            "user_id": entry.user_id,
        },
    )
