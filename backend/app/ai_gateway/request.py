"""
GatewayRequest/GatewayResponse - the entire, provider-agnostic contract
between the AI Gateway and everything above it (Prompt Builder, AI Agent
Runtime, and, through those, every future Agent) - M7.2.

Deliberately opaque in the same spirit as ActionInput/ActionOutput and
AgentInput/AgentOutput one and two layers up: `messages` is a plain
list[dict] in a role/content shape every provider's SDK can be adapted
to and from (see each ProviderClient's own translation logic), never a
provider-specific message-object type. Nothing above app/ai_gateway/
providers/ ever sees an anthropic.types.Message, an
openai.types.chat.ChatCompletion, or a google.genai.types.GenerateContentResponse.
"""
import enum
from dataclasses import dataclass, field


class ResponseFormatType(str, enum.Enum):
    TEXT = "text"
    JSON = "json"


@dataclass(frozen=True)
class ResponseFormat:
    """Structured-output requirement - one of ExecutionPolicy's fields,
    carried through unchanged by PromptBuilder.build() into the
    GatewayRequest it produces (see app.ai_agents.execution_policy).
    `json_schema` is optional even when type=JSON - not every provider's
    JSON mode requires (or supports) a schema; a ProviderClient that
    can't honor a supplied schema at all should raise InvalidRequestError
    rather than silently ignoring it."""

    type: ResponseFormatType = ResponseFormatType.TEXT
    json_schema: dict | None = None


@dataclass(frozen=True)
class ToolSpec:
    """One callable tool the model may invoke - the data SHAPE this
    milestone commits to (per the approved architecture's "must support
    tool calling without redesigning the core architecture"), not a full
    tool-execution loop. No ProviderClient in M7.2 actually invokes a
    tool on the caller's behalf; a GatewayResponse.tool_calls entry is
    handed back to the caller (ultimately the Agent, via
    Agent.interpret()) to act on, exactly like a normal text response -
    building the "call the tool, feed the result back, continue" loop is
    explicitly future work, not required for the interface to already be
    stable."""

    name: str
    description: str
    parameters_json_schema: dict


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class GatewayRequest:
    """`capability` is the ROUTING key ProviderRouter.select() reads -
    e.g. "research", "email_draft", "vision" - deliberately never a
    provider or model name; see router.py's own docstring for why this
    stays a separate vocabulary from both agent_key and provider_key.

    `model`/`temperature`/`max_tokens`/`timeout_seconds` come from
    ExecutionPolicy, assembled by PromptBuilder.build() - never set
    directly by an Agent (see app.ai_agents.base.Agent's own docstring
    for why agents never construct a GatewayRequest themselves).
    `model=None` means "let the chosen ProviderClient use its own
    settings.<PROVIDER>_DEFAULT_MODEL"; a ProviderClient with neither an
    explicit model nor a configured default must raise
    InvalidRequestError rather than guess.
    """

    capability: str
    messages: list[dict] = field(default_factory=list)
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None
    response_format: ResponseFormat | None = None
    tools: list[ToolSpec] | None = None
    stream: bool = False
    budget_usd: float | None = None
    idempotency_key: str | None = None
    # M11 (AI Provider Hierarchy). Defaults False, preserving every
    # existing caller's behavior exactly - only meaningful once
    # ProviderRouter's tier-aware routing (router.py) produces a
    # RoutingDecision with a non-empty `premium` list AND
    # settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL is True. True means "the
    # user has already explicitly approved a premium-tier call for this
    # specific request" - see errors.PremiumApprovalRequiredError's own
    # docstring for the full flow this participates in.
    premium_approved: bool = False
    # M11 (AI Provider Hierarchy) - logging/observability context only,
    # same "present for accounting, never branched on" discipline as
    # GatewayResponse.provider_key/model (see that dataclass's own
    # docstring). CompanyProfile is this codebase's existing tenant
    # boundary (no separate "workspace" concept exists yet - see
    # docs/architecture/m11-ai-provider-hierarchy-plan.md Section 3.3),
    # so `company_profile_id` is the closest honest analog to the spec's
    # "Workspace" logging field. Both optional/None-default so every
    # existing caller (and every capability that doesn't have this
    # context threaded to it yet) is unaffected.
    company_profile_id: str | None = None
    user_id: str | None = None
    # M-AIGW-1 (Provider-Neutral AI Gateway foundation) additions. Both
    # default to their exact pre-existing implicit value (0 / False), so
    # every caller that doesn't set them is unaffected.
    #
    # `document_count` - real document count for THIS request, read by
    # confidence.assess_complexity() at the one production call site that
    # previously hardcoded 0 regardless of the real request (see
    # client.py::_raise_premium_approval_required's own docstring/history) -
    # closes that dead-signal gap. Also read directly by
    # AIGateway.preflight() (see client.py) for the pre-submission check,
    # unifying what were previously two independently-passed document
    # counts (one hardcoded, one threaded from the API route) into one
    # field on the same request object.
    document_count: int = 0
    # `requires_deep_reasoning` - set by ExecutionPolicy/PromptBuilder (see
    # prompt_builder/policy.py's own docstring), never by an Agent
    # directly. Read by ProviderRouter.select() (via
    # capabilities.derive_required_capabilities()) to exclude providers
    # whose declared ProviderCapabilities.reasoning_support is False from
    # the auto-attempted chain/premium list, and by
    # confidence.assess_complexity()'s own reasoning_depth_hint parameter
    # for the premium-approval "reasons" list. No existing ExecutionPolicy
    # sets this yet - real behavior change only once a caller deliberately
    # opts in.
    requires_deep_reasoning: bool = False


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float | None = None


@dataclass(frozen=True)
class GatewayResponse:
    """`provider_key`/`model` name which provider/model actually served
    this request - present for observability/accounting only; nothing
    above app/ai_gateway/ is meant to branch its own logic on these
    values (see the approved architecture's "the rest of the system
    should never know which provider was selected")."""

    content: str | dict
    tool_calls: list[ToolCall] | None
    usage: TokenUsage
    provider_key: str
    model: str
    finish_reason: str


@dataclass(frozen=True)
class PreflightResult:
    """M-AIGW-1 (Provider-Neutral AI Gateway foundation). The Gateway's own
    public answer to "would completing this request right now need premium
    approval, and if so, what would it cost and why" - returned by
    AIGateway.preflight() (see client.py). Deliberately generic/domain-
    agnostic (no notion of "applicable" - whether a given domain's engine
    is even in "llm" mode is that domain's own concern, not the Gateway's -
    see app.research.ai_preflight's own thin wrapper for how Research
    layers its `applicable` field on top of this).

    Replaces app.research.ai_preflight's four separate direct calls into
    ProviderRouter/providers.registry/confidence/accounting with one
    Gateway-owned method call - see this milestone's own architecture
    review (docs/architecture/provider-neutral-ai-gateway-plan.md, Section
    1.2) for why that mattered."""

    approval_required: bool
    candidate_provider_key: str | None = None
    estimated_cost_usd: float | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GatewayStreamChunk:
    """One increment of a streamed response - AIGateway.stream() yields
    these. Reserved shape for a future milestone's actual streaming
    implementation (see client.py's own docstring for why `stream()`
    raises NotImplementedError in M7.2) - declared now so nothing above
    this layer needs to change when streaming is implemented."""

    delta: str
    finish_reason: str | None = None
