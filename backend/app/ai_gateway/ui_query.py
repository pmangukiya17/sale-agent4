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
    AIProviderConfigAuditRead,
    ApprovalRequestRead,
    GatewayOverviewRead,
    GatewaySettingsRead,
    ModelRoleRead,
    ProviderConfigRead,
    ProviderSummaryRead,
    RoutingDecisionRead,
    RoutingNodeRead,
    RoutingSimulationNodeRead,
    RoutingSimulationRead,
)

# M8.3 Step 4 (Routing Simulator). The AI_MODE values router._build_decision()
# actually recognizes - anything else is treated as "hybrid_recommended"
# by that function's own safe-fallback branch (see its docstring). Kept
# here (not in router.py or config.py) since this is purely an INPUT
# VALIDATION concern for the simulator's own request body - router.py
# itself deliberately never validates AI_MODE, it just falls back safely,
# and this module is the one place a caller-supplied (as opposed to
# settings-sourced) AI_MODE string first needs a clear 400 instead of a
# silently-remapped value.
VALID_AI_MODES = frozenset({"local_only", "hybrid_recommended", "automatic_premium", "premium_only"})

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


# M8.3 Step 4 (Routing Simulator). Rough, disclosed placeholder prompt
# length used ONLY for a hypothetical premium cost estimate (via
# accounting.estimate_pre_call_cost_usd()'s own "~4 chars/token" heuristic
# - see that function's own docstring) - the simulator has no real prompt
# to measure (unlike a genuine pre-submission ai_preflight check, which
# has a caller-supplied document count/char length). ~4000 chars is
# ~1,000 input tokens - a reasonable single-request order of magnitude,
# clearly caveated in RoutingSimulationRead's own docstring as an
# estimate, never presented as exact.
_SIMULATION_PLACEHOLDER_PROMPT_CHAR_LENGTH = 4000


def _simulated_request_for_capability(capability: str) -> GatewayRequest:
    """Builds the SAME shape of GatewayRequest the two live capabilities'
    own real callers actually construct (see
    app.research.ai_preflight.compute_ai_preflight()/
    app.outreach.channels.llm_agent's own ExecutionPolicy) - specifically
    so the simulator's capability-filter panel reflects a REAL requirement
    (both currently require structured_output via a JSON response_format),
    not an always-empty one. Any other capability (including "default")
    gets a plain GatewayRequest with no special requirements - honest,
    since this module has no other real capability's shape to reuse yet
    (mirrors _capability_display()'s own "unknown capability, degrade
    gracefully" convention one function up)."""
    if capability == "research_analysis":
        from app.research.analysis.llm_agent import RESPONSE_FORMAT

        return GatewayRequest(capability=capability, response_format=RESPONSE_FORMAT)
    if capability == "outreach_email_generation":
        from app.outreach.channels.llm_agent import RESPONSE_FORMAT

        return GatewayRequest(capability=capability, response_format=RESPONSE_FORMAT)
    return GatewayRequest(capability=capability)


def _default_model_safe(provider_key: str) -> str | None:
    provider_cls = PROVIDER_CLIENT_REGISTRY.get(provider_key)
    if provider_cls is None:
        return None
    try:
        return provider_cls().default_model
    except Exception:  # noqa: BLE001 - a simulator must never 500 because one provider's constructor is picky
        return None


def simulate_routing(
    capability: str,
    *,
    ai_mode_override: str | None = None,
    provider_enabled_overrides: dict[str, bool] | None = None,
) -> RoutingSimulationRead:
    """M8.3 Step 4 (Routing Simulator). READ-ONLY - never attempts a real
    provider call, never writes to any table, never changes
    `settings.AI_MODE` or any provider's real `enabled` flag.
    `ai_mode_override`/`provider_enabled_overrides` are purely
    hypothetical inputs to a pure computation
    (`app.ai_gateway.routing_simulator.build_simulation()` - see that
    module's own docstring for the full "pure core, impure shell" split
    this function is the impure half of).

    Reuses `router._build_decision()` directly (the exact function real
    routing calls, tier/AI_MODE-partitioned, already fully pure/tested by
    `tests/test_ai_provider_hierarchy_pure.py`) rather than
    `router.ProviderRouter.select()` - this function needs the
    PRE-capability-filter decision so `build_simulation()` can attach a
    capability-mismatch exclusion to its own node (see that function's
    own docstring for why `ProviderRouter.select()`'s already-filtered
    result wouldn't work for this).

    `capability` may be any string, including one not in
    `CAPABILITY_PROVIDER_PREFERENCE` - falls back to the "default"
    preference entry, exactly like real routing does."""
    from app.ai_gateway.accounting import estimate_pre_call_cost_usd
    from app.ai_gateway.capabilities import derive_required_capabilities
    from app.ai_gateway.router import _DEFAULT_CAPABILITY_KEY, _build_decision
    from app.ai_gateway.routing_simulator import build_simulation
    from app.core.config import settings  # lazy - matches router.py's own discipline

    ai_mode = ai_mode_override or settings.AI_MODE
    preference = CAPABILITY_PROVIDER_PREFERENCE.get(capability, CAPABILITY_PROVIDER_PREFERENCE[_DEFAULT_CAPABILITY_KEY])
    decision = _build_decision(preference, ai_mode)

    request = _simulated_request_for_capability(capability)
    required = derive_required_capabilities(request)
    provider_level = {key: cls.capabilities for key, cls in PROVIDER_CLIENT_REGISTRY.items()}

    def _estimate_cost(provider_key: str) -> float | None:
        model = _default_model_safe(provider_key)
        if model is None:
            return None
        return estimate_pre_call_cost_usd(
            provider_key=provider_key, model=model, prompt_char_length=_SIMULATION_PLACEHOLDER_PROMPT_CHAR_LENGTH
        )

    result = build_simulation(
        decision,
        required,
        provider_level=provider_level,
        is_configured=_is_configured_safe,
        overrides=provider_enabled_overrides,
        require_premium_approval=settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL,
        tier_of=lambda key: tier_of(key).value,
        label_of=lambda key: _PROVIDER_LABELS.get(key, key),
        price_of=_provider_default_prices,
        estimate_cost=_estimate_cost,
    )

    feature_label, _agent = _capability_display(capability)
    requested_capabilities = []
    if required.structured_output:
        requested_capabilities.append("structured_output")
    if required.tool_calling:
        requested_capabilities.append("tool_calling")
    if required.reasoning_support:
        requested_capabilities.append("reasoning_support")

    return RoutingSimulationRead(
        capability=capability,
        feature_label=feature_label,
        ai_mode_used=ai_mode,
        requested_capabilities=requested_capabilities,
        capability_excluded=result.capability_excluded,
        nodes=[
            RoutingSimulationNodeRead(
                provider_key=n.provider_key,
                label=_PROVIDER_LABELS.get(n.provider_key, n.provider_key),
                tier=n.tier,
                role=n.role,
                position=n.position,
                state=n.state,
                reason=n.reason,
                configured=n.configured,
                overridden=n.overridden,
                cost_per_1k_input_usd=n.cost_per_1k_input_usd,
                cost_per_1k_output_usd=n.cost_per_1k_output_usd,
                estimated_cost_usd=n.estimated_cost_usd,
            )
            for n in result.nodes
        ],
        outcome=result.outcome,
        outcome_detail=result.outcome_detail,
    )


def get_provider_config(db: Session, provider_key: str) -> ProviderConfigRead | None:
    """M8.3 Step 2 (Provider Management). GET/PUT
    /ai-gateway/providers/{provider_key}/config's read projection - the
    override ROW itself (see ProviderConfigRead's own docstring for why
    this differs from ProviderSummaryRead's EFFECTIVE/resolved view).
    Returns None only if `provider_key` isn't a real registered provider
    at all (the route below 404s in that case, mirroring
    get_provider()'s own existing precedent) - a real provider_key with
    no saved row yet still gets a row here, synthesized as "no override"
    (`enabled=True`, everything else empty), exactly matching what
    `resolve_provider_config()` itself falls back to."""
    if provider_key not in PROVIDER_CLIENT_REGISTRY:
        return None

    from app.models.ai_provider_config import AIProviderConfig

    row = db.query(AIProviderConfig).filter(AIProviderConfig.provider_key == provider_key).first()
    if row is None:
        return ProviderConfigRead(
            provider_key=provider_key,
            enabled=True,
            has_api_key=False,
            base_url=None,
            default_model=None,
            extra_settings={},
            updated_at=None,
            updated_by_user_email=None,
        )

    return ProviderConfigRead(
        provider_key=row.provider_key,
        enabled=row.enabled,
        has_api_key=row.encrypted_api_key is not None,
        base_url=row.base_url,
        default_model=row.default_model,
        extra_settings=dict(row.extra_settings or {}),
        updated_at=row.updated_at,
        updated_by_user_email=row.updated_by_user.email if row.updated_by_user else None,
    )


def list_provider_config_audit(db: Session, provider_key: str, *, limit: int = 50) -> list[AIProviderConfigAuditRead]:
    """M8.3 Step 2. GET /ai-gateway/providers/{provider_key}/config/audit -
    the CEO's "lightweight configuration audit history" requirement,
    read-only, most-recent-first. Not scoped to the calling user - a
    provider's configuration is instance-wide infrastructure (same
    reasoning ProviderSummaryRead's own module docstring already gives
    for provider-level stats being global, not per-company), so its
    change history is too; the admin gate on the route itself (not this
    function) is what restricts who can call this at all."""
    from app.models.ai_provider_config_audit import AIProviderConfigAudit

    rows = (
        db.query(AIProviderConfigAudit)
        .filter(AIProviderConfigAudit.provider_key == provider_key)
        .order_by(AIProviderConfigAudit.changed_at.desc())
        .limit(limit)
        .all()
    )
    return [
        AIProviderConfigAuditRead(
            id=row.id,
            provider_key=row.provider_key,
            changed_at=row.changed_at,
            changed_by_user_email=row.changed_by_user.email if row.changed_by_user else None,
            field_changes=row.field_changes,
        )
        for row in rows
    ]


def get_model_role(db: Session, role_name: str) -> ModelRoleRead | None:
    """M8.3 Step 3. Single-row read used by the PUT/GET-by-name routes -
    returns None if `role_name` has no saved `AIModelRole` row (unlike
    Provider Management's `get_provider_config()`, there is no "no row
    yet -> synthesized default" here - see `list_model_roles()`'s own
    docstring for why role names are open-ended, not a fixed universe)."""
    from app.models.ai_model_role import AIModelRole

    row = db.query(AIModelRole).filter(AIModelRole.role_name == role_name).first()
    if row is None:
        return None
    return ModelRoleRead(
        role_name=row.role_name,
        model=row.model,
        enabled=row.enabled,
        updated_at=row.updated_at,
        updated_by_user_email=row.updated_by_user.email if row.updated_by_user else None,
    )


def list_model_roles(db: Session) -> list[ModelRoleRead]:
    """M8.3 Step 3 (Model Role Management). GET /ai-gateway/model-roles's
    read projection - every `AIModelRole` row that actually exists,
    ordered by role_name, via `local_model_policy.list_model_roles()`.
    Unlike Provider Management, there's no fixed universe of role names to
    synthesize a "no override yet" placeholder for - role names are
    open-ended (a brand-new role IS created by the first save), so an
    empty DB table simply returns an empty list here; the CODE-level
    `LOCAL_MODEL_ROLES`/`CAPABILITY_LOCAL_MODEL_ROLE` tables remain visible
    read-only via `GatewaySettingsRead` regardless of what's in this
    table. Takes the request-scoped `db: Session` FastAPI already resolved
    - same convention `get_provider_config()`/`list_provider_config_audit()`
    already use - rather than opening a second connection per call."""
    from app.ai_gateway.local_model_policy import list_model_roles as _list_model_roles

    rows = _list_model_roles(db)
    return [
        ModelRoleRead(
            role_name=row.role_name,
            model=row.model,
            enabled=row.enabled,
            updated_at=row.updated_at,
            updated_by_user_email=row.updated_by_user.email if row.updated_by_user else None,
        )
        for row in rows
    ]


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
