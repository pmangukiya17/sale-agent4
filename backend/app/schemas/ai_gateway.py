import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProviderSummaryRead(BaseModel):
    """M8.2. One row from GET /ai-gateway/providers or
    /ai-gateway/providers/{provider_key} - built entirely from
    app.ai_gateway.providers.registry.PROVIDER_CLIENT_REGISTRY,
    app.ai_gateway.tiers, and each ProviderClient's own
    is_configured()/default_model/capabilities - no database read at all
    (this is live, real-time provider configuration, not historical data).
    Snake_case, matching every other schema in this codebase
    (app/schemas/*.py) - the frontend's camelCase GatewayDataProvider
    contract is translated by ApiGatewayProvider.ts, not by this schema."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    tier: str
    status: str
    default_model: str | None
    cost_per_1k_input_usd: float | None
    cost_per_1k_output_usd: float | None
    avg_latency_ms: float | None
    requests_today: int
    capabilities: list[str]


class GatewayOverviewRead(BaseModel):
    """M8.2. GET /ai-gateway/overview. `gateway_health` is derived only
    from the real, disclosed signal this codebase has - whether at least
    one provider is_configured() - never a fabricated "degraded" state (no
    live per-provider network health check exists anywhere in this
    codebase). `running_agents` is a real, freshly-computed COUNT of
    WorkflowInstance rows in RUNNING status across the caller's own
    companies - a single query per request, not a polled/pushed value."""

    gateway_health: str
    active_providers: int
    total_providers: int
    running_agents: int
    requests_today: int
    success_rate_pct: float
    estimated_cost_today_usd: float
    premium_requests_today: int


class ActivityLogEntryRead(BaseModel):
    """M8.2. GET /ai-gateway/activity. One row per
    app.models.ai_request_log.AIRequestLog, scoped to the caller's own
    companies (see app.ai_gateway.ui_query's own module docstring for the
    isolation rule). `chain_summary` is a SINGLE-ROW-derived one-line
    description, not a full multi-provider chain replay - each
    AIRequestLog row already represents one final outcome (success, a
    terminal failure, or a premium-approval-required event), never the
    full sequence of providers AIGateway._walk() may have attempted
    first (that intermediate detail is not persisted - see
    request_log.py's own docstring)."""

    id: uuid.UUID
    timestamp: datetime
    feature: str
    agent: str
    capability: str
    provider_key: str | None
    model: str | None
    cost_usd: float | None
    latency_ms: float | None
    status: str
    company_name: str | None
    chain_summary: str
    error_message: str | None


class ApprovalRequestRead(BaseModel):
    """M8.2. GET /ai-gateway/approvals. Read-only, per the approved M8.2
    scope - see app.ai_gateway.ui_query's own module docstring for why
    this reflects PAST premium-approval-required EVENTS (from
    AIRequestLog, error_type='PremiumApprovalRequiredError'), not a live
    blocking queue - this codebase's premium-approval gate is a
    synchronous pre-flight check (AIGateway.preflight() /
    PremiumApprovalRequiredError), not a durable, still-pending request a
    human can act on later. `waiting_minutes` is reinterpreted honestly as
    "minutes since this was flagged," not "minutes still blocking a
    request" - the underlying request has already either been resubmitted
    with premium_approved=True or abandoned by the time this is viewed."""

    id: uuid.UUID
    feature: str
    reason: str
    provider_key: str
    model: str
    estimated_cost_usd: float
    requested_at: datetime
    waiting_minutes: float
    company_name: str | None


class RoutingNodeRead(BaseModel):
    id: str
    label: str
    state: str
    detail: str | None = None


class RoutingDecisionRead(BaseModel):
    """M8.2. GET /ai-gateway/routing. A REAL-TIME POLICY PREVIEW - built by
    calling the actual app.ai_gateway.router.ProviderRouter.select() for
    each live capability right now, not a replay of one specific past
    request's actual chain (this codebase's AIRequestLog persists only the
    FINAL outcome of an attempt sequence, never the full ordered chain
    that was tried - see ActivityLogEntryRead's own docstring). This is a
    disclosed, necessary adaptation of the M8.1 mock's "replay a real
    RoutingDecision" framing - it still reflects genuine live provider
    router / configuration state, just computed fresh per request instead
    of read from history."""

    id: str
    capability: str
    timestamp: datetime
    nodes: list[RoutingNodeRead]
    outcome: str


class GatewaySettingsRead(BaseModel):
    """M8.2. GET /ai-gateway/settings - read-only. A direct, live
    projection of the actual settings AIGateway/ProviderRouter read at
    call time (app.core.config.settings, app.ai_gateway.router's
    CAPABILITY_PROVIDER_PREFERENCE, app.ai_gateway.local_model_policy's
    LOCAL_MODEL_ROLES) - never a second, independently-editable copy.
    Settings PERSISTENCE (accepting a PUT to change any of these) is
    explicitly out of scope for M8.2 - see app/api/routes/ai_gateway.py's
    own docstring."""

    ai_mode: str
    require_premium_approval: bool
    max_attempts_per_provider: int
    default_timeout_seconds: float
    capability_provider_preference: dict[str, list[str]]
    local_model_roles: dict[str, str | None]
    capability_local_model_role: dict[str, list[str]]
