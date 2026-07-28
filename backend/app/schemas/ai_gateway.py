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


class ProviderConfigWrite(BaseModel):
    """M8.3 (AI Gateway Management & Control, Step 2 - Provider
    Management). Request body for `PUT /ai-gateway/providers/{provider_key}/config`.
    Field-for-field mirrors `app.ai_gateway.provider_config.save_provider_config()`'s
    own signature - every field left as `None` (the default) means
    "leave this field alone," never "clear it." `clear_api_key`/
    `clear_base_url`/`clear_default_model` are how a caller distinguishes
    "leave alone" from "clear back to deferring to `.env`" - see that
    function's own docstring for why `None` alone is ambiguous for those
    three fields specifically.

    `api_key`, once accepted here, is NEVER echoed back by any read
    response - see `ProviderConfigRead.has_api_key` for the only signal
    a caller gets back about whether one is stored."""

    enabled: bool | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    base_url: str | None = None
    clear_base_url: bool = False
    default_model: str | None = None
    clear_default_model: bool = False
    extra_settings: dict | None = None


class ProviderConfigRead(BaseModel):
    """M8.3 Step 2. GET/PUT response for one provider's DB-backed
    configuration override state - distinct from `ProviderSummaryRead`
    (which reflects the EFFECTIVE, resolved value - DB override merged
    over `.env` fallback). This schema reflects the override ROW itself:
    a provider with no saved override at all still returns a row here
    (`enabled=True`, everything else `None`/empty), mirroring
    `resolve_provider_config()`'s own "no row = pure fallback" behavior,
    so the Provider Management form has something to render even before
    an operator has ever saved anything.

    `has_api_key` is the only signal about credential state - the actual
    decrypted value is never returned by any read endpoint."""

    provider_key: str
    enabled: bool
    has_api_key: bool
    base_url: str | None
    default_model: str | None
    extra_settings: dict
    updated_at: datetime | None
    updated_by_user_email: str | None


class AIProviderConfigAuditRead(BaseModel):
    """M8.3 Step 2. GET /ai-gateway/providers/{provider_key}/config/audit -
    the CEO's explicit "lightweight configuration audit history"
    requirement, exposed read-only. One row per
    `app.models.ai_provider_config_audit.AIProviderConfigAudit` - see that
    model's own docstring for why `field_changes` never contains a
    plaintext `api_key` value."""

    id: uuid.UUID
    provider_key: str
    changed_at: datetime
    changed_by_user_email: str | None
    field_changes: dict


class ConnectionTestResultRead(BaseModel):
    """M8.3 Step 2. POST /ai-gateway/providers/{provider_key}/test-connection
    response - mirrors `app.ai_gateway.providers.base.ConnectionTestResult`
    field for field, plus the `provider_key` itself (the dataclass doesn't
    carry it, the caller already knows which provider it asked about)."""

    provider_key: str
    success: bool
    message: str
    latency_ms: float | None
    available_models: list[str] | None


class ModelRoleWrite(BaseModel):
    """M8.3 (AI Gateway Management & Control, Step 3 - Model Role
    Management). Request body for
    `PUT /ai-gateway/model-roles/{role_name}`. Field-for-field mirrors
    `app.ai_gateway.local_model_policy.save_model_role()`'s own signature.
    `model` is required when creating a brand-new role (see that
    function's own docstring); optional on an update, where `None` means
    "leave the currently-stored model alone." """

    model: str | None = None
    enabled: bool | None = None


class ModelRoleRead(BaseModel):
    """M8.3 Step 3. GET/PUT response for one semantic role's DB-backed
    override row - distinct from the CODE-level `LOCAL_MODEL_ROLES`/
    `CAPABILITY_LOCAL_MODEL_ROLE` tables (still exposed read-only via
    `GatewaySettingsRead`). A role with no saved DB row is simply absent
    from `GET /ai-gateway/model-roles` - unlike Provider Management,
    there's no "one row per possible role" to synthesize, since role
    names themselves are open-ended (an admin creating "coding" for the
    first time IS the act of adding a new row)."""

    role_name: str
    model: str
    enabled: bool
    updated_at: datetime | None
    updated_by_user_email: str | None


class RoutingSimulationRequest(BaseModel):
    """M8.3 (AI Gateway Management & Control, Step 4 - Routing Simulator).
    Request body for `POST /ai-gateway/routing/simulate`. READ-ONLY -
    this endpoint never mutates any setting, never attempts a real
    provider call; `ai_mode_override`/`provider_enabled_overrides` are
    purely hypothetical inputs to a pure computation (see
    `app.ai_gateway.routing_simulator.build_simulation()`'s own docstring),
    never persisted anywhere. `ai_mode_override` left `None` uses the
    real, live `settings.AI_MODE`. `provider_enabled_overrides` left
    `None`/empty uses each provider's real, live `is_configured()` value
    for every provider; a provider_key present in the dict has its
    EFFECTIVE (simulated) enabled state taken from the override instead -
    see `RoutingSimulationNodeRead.overridden` for how a caller can tell
    which nodes reflect a hypothetical rather than a real fact."""

    capability: str
    ai_mode_override: str | None = None
    provider_enabled_overrides: dict[str, bool] | None = None


class RoutingSimulationNodeRead(BaseModel):
    """M8.3 Step 4. One candidate provider_key in the FULL preference
    order for this capability - see
    `app.ai_gateway.routing_simulator.SimulationNode`'s own docstring for
    field meanings. `state` is one of: "would_call" (this is the provider
    that would actually serve the request), "requires_approval" (a
    premium candidate gated behind the approval prompt),
    "skipped_not_configured", "skipped_capability_mismatch", or
    "skipped_not_reached" (an earlier candidate already satisfied the
    request)."""

    provider_key: str
    label: str
    tier: str
    role: str
    position: int
    state: str
    reason: str
    configured: bool
    overridden: bool
    cost_per_1k_input_usd: float | None
    cost_per_1k_output_usd: float | None
    estimated_cost_usd: float | None


class RoutingSimulationRead(BaseModel):
    """M8.3 Step 4. Response for `POST /ai-gateway/routing/simulate` - the
    full, explained routing decision for one capability, under whatever
    real-or-hypothetical AI_MODE/provider-enabled inputs were given.
    `requested_capabilities` is which of structured_output/tool_calling/
    reasoning_support this (simulated) request actually needs -
    `capability_excluded` is which candidate provider_keys were removed
    from consideration because they don't support one of those (mirrors
    `RoutingDecision.capability_excluded` - see router.py's own
    docstring)."""

    capability: str
    feature_label: str
    ai_mode_used: str
    requested_capabilities: list[str]
    capability_excluded: list[str]
    nodes: list[RoutingSimulationNodeRead]
    outcome: str
    outcome_detail: str


class CapabilityValuesRead(BaseModel):
    """M8.3 (AI Gateway Management & Control, Step 5 - Provider
    Capability Viewer). Mirrors `app.ai_gateway.capabilities.ProviderCapabilities`
    field-for-field - the SAME dataclass every routing/capability-
    filtering decision already reads through
    (`router.ProviderRouter.select()`, `capabilities.filter_capable()`),
    never a second, independently-maintained capability description.
    `structured_output`/`tool_calling`/`streaming`/`vision`/`embeddings`/
    `reasoning_support` are booleans (unsupported is an explicit `false`,
    never an absent key); `max_context_tokens`/`max_output_tokens` are
    informational token limits, `None` when not yet disclosed for that
    provider/model - see `ProviderCapabilities`' own docstring for why
    these two are advisory rather than a pass/fail gate this milestone."""

    structured_output: bool
    tool_calling: bool
    streaming: bool
    vision: bool
    embeddings: bool
    reasoning_support: bool
    max_context_tokens: int | None
    max_output_tokens: int | None


class ProviderCapabilityRead(BaseModel):
    """M8.3 Step 5. One row of `GET /ai-gateway/capabilities` - one
    registered provider_key's full capability picture, built entirely
    from `PROVIDER_CLIENT_REGISTRY`/`capabilities.py` (the same
    centralized source every routing decision already reads) - a future
    seventh provider that registers itself in `PROVIDER_CLIENT_REGISTRY`
    with its own `capabilities: ClassVar[ProviderCapabilities]` appears
    here automatically, no new code in this schema or its route.

    `provider_level` is the provider's class-level default - a fixed fact
    about its wire-format/SDK integration, true regardless of which model
    is configured. `effective` is `provider_level` merged with any
    per-model override registered for `default_model` specifically (via
    `capabilities.register_capability_override()`) - identical to
    `provider_level` whenever no such override exists (true for every
    provider today - see `ProviderCapabilityRead`'s own module-level
    disclosure). `has_model_override`/`overridden_fields` are the
    explicit signal a UI needs to visually distinguish "this capability
    is a fixed provider-level fact" from "this specific model's real
    behavior differs from its provider's own default" - never left for a
    caller to infer by diffing the two objects itself."""

    provider_key: str
    label: str
    tier: str
    default_model: str | None
    provider_level: CapabilityValuesRead
    effective: CapabilityValuesRead
    has_model_override: bool
    overridden_fields: list[str]


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
