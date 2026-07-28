"""
ui_query.py - M8.2 (AI Gateway Backend Integration). The read-only query
layer behind app/api/routes/ai_gateway.py - kept inside app.ai_gateway
itself (not a new top-level package) since every function here is a thin
projection over data app.ai_gateway already owns (PROVIDER_CLIENT_REGISTRY,
tiers, capabilities, ProviderRouter, settings) plus the new
AIRequestLog table this milestone adds. Nothing here duplicates domain
logic that already lives in router.py/tiers.py/capabilities.py/accounting.py -
every function is a caller of those, never a reimplementation.

ISOLATION RULE (Track A discipline, applied to this new zone): Activity/
Approvals/Overview's operational numbers (requests, cost, approvals) are
scoped to the CALLING USER's own companies only -
`_owned_company_profile_ids()` below, and every query that reads
AIRequestLog filters `company_profile_id IN (...)`. AIRequestLog rows with
company_profile_id=None (a capability that hasn't threaded that context
yet - see that model's own docstring) are EXCLUDED from every user-scoped
view, never shown to any user - the safe default when a row's owner can't
be determined. Provider-level stats (ProviderSummaryRead.requests_today/
avg_latency_ms) are the one deliberate exception - aggregated GLOBALLY,
not per-user, because provider CREDENTIALS themselves are instance-wide
settings (app.core.config.settings), not per-company data; the provider
registry itself is genuinely shared infrastructure, not one user's data.

HONESTY NOTES (both disclosed in the relevant schema's own docstring too):
  - Routing is a REAL-TIME POLICY PREVIEW (calls ProviderRouter.select()
    fresh, for each live capability), not a replay of one specific past
    request - this codebase's AIRequestLog persists only a final outcome
    per attempt sequence, never the full ordered chain that was tried.
  - Approvals reflects PAST premium-approval-required EVENTS, not a live
    blocking queue - this codebase's premium-approval gate is a
    synchronous pre-flight check, not a durable, still-actionable request.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai_gateway.accounting import _PROVIDER_DEFAULT_PRICE_USD_PER_1K
from app.ai_gateway.local_model_policy import CAPABILITY_LOCAL_MODEL_ROLE, LOCAL_MODEL_ROLES
from app.ai_gateway.providers.registry import PROVIDER_CLIENT_REGISTRY
from app.ai_gateway.request import GatewayRequest
from app.ai_gateway.router import CAPABILITY_PROVIDER_PREFERENCE, ProviderRouter
from app.ai_gateway.tiers import tier_of
from app.models.ai_request_log import AIRequestLog
from app.models.company_profile import CompanyProfile
from app.models.enums import WorkflowInstanceStatus
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.schemas.ai_gateway import (
    ActivityLogEntryRead,
    ApprovalRequestRead,
    GatewayOverviewRead,
    GatewaySettingsRead,
    ProviderSummaryRead,
    RoutingDecisionRead,
    RoutingNodeRead,
)

# Cosmetic display labels only - never read by any routing/capability
# decision (that stays entirely inside router.py/tiers.py/capabilities.py).
# Mirrors frontend/src/ai-gateway/identity/providerIdentity.ts's own
# PROVIDER_IDENTITIES field-for-field, since this is the backend half of
# the same identity concept (both sides deliberately kept in sync by hand,
# same "no shared codegen" precedent every other frontend/backend schema
# pair in this codebase already has).
_PROVIDER_LABELS: dict[str, str] = {
    "local_ollama": "Ollama",
    "groq": "Groq",
    "gemini_ai_studio": "Gemini AI Studio",
    "gemini": "Gemini",
    "claude": "Claude",
    "openai": "OpenAI",
}

_CAPABILITY_DISPLAY: dict[str, tuple[str, str]] = {
    # capability -> (feature label, agent label) - cosmetic only.
    "research_analysis": ("Prospect Research", "Research Analysis Agent"),
    "outreach_email_generation": ("Email Drafting", "Outreach Email Agent"),
    "default": ("General", "Default Agent"),
}


def _capability_display(capability: str) -> tuple[str, str]:
    if capability in _CAPABILITY_DISPLAY:
        return _CAPABILITY_DISPLAY[capability]
    # Forward-compatible fallback for any capability not yet given a
    # cosmetic label - never crashes on an unrecognized (e.g. newly-wired)
    # capability string, same "unknown is normal, degrade gracefully"
    # convention this package already uses throughout.
    label = capability.replace("_", " ").title()
    return label, label


def _owned_company_profile_ids(db: Session, user: User) -> list[uuid.UUID]:
    rows = db.query(CompanyProfile.id).filter(CompanyProfile.owner_user_id == user.id).all()
    return [row[0] for row in rows]


def _provider_capability_labels(provider_key: str) -> list[str]:
    provider_cls = PROVIDER_CLIENT_REGISTRY.get(provider_key)
    if provider_cls is None:
        return []
    caps = provider_cls.capabilities
    labels = []
    if caps.structured_output:
        labels.append("structured_output")
    if caps.tool_calling:
        labels.append("tool_calling")
    if caps.streaming:
        labels.append("streaming")
    if caps.vision:
        labels.append("vision")
    if caps.reasoning_support:
        labels.append("reasoning_support")
    return labels


def _provider_default_prices(provider_key: str) -> tuple[float | None, float | None]:
    """Best-effort, provider-level (not per-exact-model) price - mirrors
    accounting.estimate_cost_usd()'s own provider-default fallback tier,
    but without a real model id (this is a catalog view, not a
    per-request estimate) - reads the provider-level default table
    directly, same "informational estimate, may not match the exact
    configured model" disclosure accounting.py's own docstring already
    makes."""
    prices = _PROVIDER_DEFAULT_PRICE_USD_PER_1K.get(provider_key)
    if prices is None:
        return None, None
    return prices


def _requests_today_and_latency(db: Session, provider_key: str) -> tuple[int, float | None]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    row = (
        db.query(func.count(AIRequestLog.id), func.avg(AIRequestLog.duration_ms))
        .filter(AIRequestLog.provider_key == provider_key, AIRequestLog.occurred_at >= since)
        .one()
    )
    count, avg_latency = row
    return int(count or 0), float(avg_latency) if avg_latency is not None else None


def _provider_summary(db: Session, provider_key: str) -> ProviderSummaryRead | None:
    provider_cls = PROVIDER_CLIENT_REGISTRY.get(provider_key)
    if provider_cls is None:
        return None
    client = provider_cls()
    requests_today, avg_latency_ms = _requests_today_and_latency(db, provider_key)
    prompt_price, completion_price = _provider_default_prices(provider_key)
    return ProviderSummaryRead(
        key=provider_key,
        label=_PROVIDER_LABELS.get(provider_key, provider_key),
        tier=tier_of(provider_key).value,
        status="connected" if client.is_configured() else "not_configured",
        default_model=client.default_model,
        cost_per_1k_input_usd=prompt_price,
        cost_per_1k_output_usd=completion_price,
        avg_latency_ms=avg_latency_ms,
        requests_today=requests_today,
        capabilities=_provider_capability_labels(provider_key),
    )


def list_providers(db: Session) -> list[ProviderSummaryRead]:
    return [_provider_summary(db, key) for key in PROVIDER_CLIENT_REGISTRY]


def get_provider(db: Session, provider_key: str) -> ProviderSummaryRead | None:
    return _provider_summary(db, provider_key)


def get_overview(db: Session, user: User) -> GatewayOverviewRead:
    owned_ids = _owned_company_profile_ids(db, user)
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    configured_count = sum(1 for key in PROVIDER_CLIENT_REGISTRY if PROVIDER_CLIENT_REGISTRY[key]().is_configured())
    total_count = len(PROVIDER_CLIENT_REGISTRY)

    running_agents = 0
    if owned_ids:
        running_agents = (
            db.query(func.count(WorkflowInstance.id))
            .filter(
                WorkflowInstance.company_profile_id.in_(owned_ids),
                WorkflowInstance.status == WorkflowInstanceStatus.RUNNING,
            )
            .scalar()
            or 0
        )

    requests_today = 0
    success_rate_pct = 0.0
    estimated_cost_today_usd = 0.0
    premium_requests_today = 0
    if owned_ids:
        rows = (
            db.query(AIRequestLog)
            .filter(AIRequestLog.company_profile_id.in_(owned_ids), AIRequestLog.occurred_at >= since)
            .all()
        )
        requests_today = len(rows)
        if requests_today:
            success_rate_pct = round(100 * sum(1 for r in rows if r.success) / requests_today, 1)
        estimated_cost_today_usd = round(sum(r.cost_usd or 0.0 for r in rows), 4)
        premium_requests_today = sum(1 for r in rows if r.tier == "premium")

    return GatewayOverviewRead(
        gateway_health="healthy" if configured_count > 0 else "down",
        active_providers=configured_count,
        total_providers=total_count,
        running_agents=int(running_agents),
        requests_today=requests_today,
        success_rate_pct=success_rate_pct,
        estimated_cost_today_usd=estimated_cost_today_usd,
        premium_requests_today=premium_requests_today,
    )


def _status_of(entry: AIRequestLog) -> str:
    if entry.error_type == "PremiumApprovalRequiredError":
        return "waiting"
    return "success" if entry.success else "failed"


def _chain_summary(entry: AIRequestLog) -> str:
    if entry.error_type == "PremiumApprovalRequiredError":
        return f"Awaiting premium approval ({entry.model or 'model unknown'})"
    if entry.success:
        provider_label = _PROVIDER_LABELS.get(entry.provider_key or "", entry.provider_key or "unknown provider")
        return f"{provider_label} ({entry.tier or 'unknown tier'} tier)"
    return f"Failed on {entry.provider_key or 'unknown provider'}: {entry.error_type or 'unknown error'}"


def list_activity(db: Session, user: User, *, limit: int = 100) -> list[ActivityLogEntryRead]:
    owned_ids = _owned_company_profile_ids(db, user)
    if not owned_ids:
        return []
    company_names = {row.id: row.name for row in db.query(CompanyProfile).filter(CompanyProfile.id.in_(owned_ids))}
    rows = (
        db.query(AIRequestLog)
        .filter(AIRequestLog.company_profile_id.in_(owned_ids))
        .order_by(AIRequestLog.occurred_at.desc())
        .limit(limit)
        .all()
    )
    entries = []
    for row in rows:
        feature, agent = _capability_display(row.capability)
        entries.append(
            ActivityLogEntryRead(
                id=row.id,
                timestamp=row.occurred_at,
                feature=feature,
                agent=agent,
                capability=row.capability,
                provider_key=row.provider_key,
                model=row.model,
                cost_usd=row.cost_usd,
                latency_ms=row.duration_ms,
                status=_status_of(row),
                company_name=company_names.get(row.company_profile_id),
                chain_summary=_chain_summary(row),
                error_message=row.error_type,
            )
        )
    return entries


def list_approvals(db: Session, user: User, *, limit: int = 50) -> list[ApprovalRequestRead]:
    owned_ids = _owned_company_profile_ids(db, user)
    if not owned_ids:
        return []
    company_names = {row.id: row.name for row in db.query(CompanyProfile).filter(CompanyProfile.id.in_(owned_ids))}
    rows = (
        db.query(AIRequestLog)
        .filter(
            AIRequestLog.company_profile_id.in_(owned_ids),
            AIRequestLog.error_type == "PremiumApprovalRequiredError",
        )
        .order_by(AIRequestLog.occurred_at.desc())
        .limit(limit)
        .all()
    )
    now = datetime.now(timezone.utc)
    approvals = []
    for row in rows:
        feature, _agent = _capability_display(row.capability)
        occurred_at = row.occurred_at if row.occurred_at.tzinfo else row.occurred_at.replace(tzinfo=timezone.utc)
        minutes_since = max(0.0, (now - occurred_at).total_seconds() / 60.0)
        approvals.append(
            ApprovalRequestRead(
                id=row.id,
                feature=feature,
                reason=f"Local/free tier exhausted for '{row.capability}'; premium approval required.",
                provider_key=row.provider_key or "unknown",
                model=row.model or "unknown",
                estimated_cost_usd=row.cost_usd or 0.0,
                requested_at=row.occurred_at,
                waiting_minutes=round(minutes_since, 1),
                company_name=company_names.get(row.company_profile_id),
            )
        )
    return approvals


_LIVE_ROUTING_CAPABILITIES = ["research_analysis", "outreach_email_generation"]


def _is_configured_safe(provider_key: str) -> bool:
    provider_cls = PROVIDER_CLIENT_REGISTRY.get(provider_key)
    if provider_cls is None:
        return False
    return provider_cls().is_configured()


def _routing_preview_for_capability(capability: str) -> RoutingDecisionRead:
    from app.core.config import settings  # lazy - matches router.py's own discipline

    decision = ProviderRouter.select(GatewayRequest(capability=capability))
    nodes: list[RoutingNodeRead] = []
    reached = False
    for key in decision.chain():
        configured = _is_configured_safe(key)
        label = _PROVIDER_LABELS.get(key, key)
        if reached:
            nodes.append(RoutingNodeRead(id=key, label=label, state="skipped", detail="not reached"))
        elif configured:
            nodes.append(RoutingNodeRead(id=key, label=label, state="terminal-success", detail="currently configured"))
            reached = True
        else:
            nodes.append(RoutingNodeRead(id=key, label=label, state="skipped", detail="not configured"))

    outcome = "success" if reached else "failed"
    if not reached and decision.premium:
        premium_key = decision.premium[0]
        label = _PROVIDER_LABELS.get(premium_key, premium_key)
        if settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL:
            nodes.append(RoutingNodeRead(id=premium_key, label=label, state="terminal-waiting", detail="requires premium approval"))
            outcome = "waiting"
        elif _is_configured_safe(premium_key):
            nodes.append(RoutingNodeRead(id=premium_key, label=label, state="terminal-success", detail="premium, gate disabled"))
            outcome = "success"
        else:
            nodes.append(RoutingNodeRead(id=premium_key, label=label, state="terminal-failed", detail="not configured"))
            outcome = "failed"

    feature_label, _agent = _capability_display(capability)
    return RoutingDecisionRead(
        id=capability,
        capability=feature_label,
        timestamp=datetime.now(timezone.utc),
        nodes=nodes,
        outcome=outcome,
    )


def list_routing_decisions() -> list[RoutingDecisionRead]:
    return [_routing_preview_for_capability(capability) for capability in _LIVE_ROUTING_CAPABILITIES]


def get_settings() -> GatewaySettingsRead:
    from app.core.config import settings  # lazy - matches router.py's own discipline

    local_model_roles = {role: getattr(settings, attr, None) for role, attr in LOCAL_MODEL_ROLES.items()}
    return GatewaySettingsRead(
        ai_mode=settings.AI_MODE,
        require_premium_approval=settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL,
        max_attempts_per_provider=settings.AI_GATEWAY_MAX_ATTEMPTS_PER_PROVIDER,
        default_timeout_seconds=settings.AI_GATEWAY_DEFAULT_TIMEOUT_SECONDS,
        capability_provider_preference=dict(CAPABILITY_PROVIDER_PREFERENCE),
        local_model_roles=local_model_roles,
        capability_local_model_role=dict(CAPABILITY_LOCAL_MODEL_ROLE),
    )
