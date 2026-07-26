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
class GatewayStreamChunk:
    """One increment of a streamed response - AIGateway.stream() yields
    these. Reserved shape for a future milestone's actual streaming
    implementation (see client.py's own docstring for why `stream()`
    raises NotImplementedError in M7.2) - declared now so nothing above
    this layer needs to change when streaming is implemented."""

    delta: str
    finish_reason: str | None = None
