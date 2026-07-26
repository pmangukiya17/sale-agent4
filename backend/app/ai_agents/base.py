"""
The Agent contract - M7.2. Deliberately TWO methods, not the single
`run()` originally sketched in the pre-refinement architecture draft.

Why the split: the approved refinements require that "Agents should not
hardcode: provider, model, temperature, token limits, timeout, budget,
structured output requirements" and that the Prompt Builder - not the
Agent - "assembles [context] into the final prompt/messages sent to the
Gateway." A single `run()` method that internally called PromptBuilder
and AIGateway itself would still let a concrete Agent implementation
reach into those calls and pass its own model/temperature/messages,
because nothing about a single method's signature prevents it. Splitting
Agent into `build_context()` (business content only - returns a
PromptContext, never touches GatewayRequest/ExecutionPolicy/provider/
model) and `interpret()` (reads back a GatewayResponse - never
constructs one) makes both refinements structurally enforced rather than
just documented convention: an Agent implementation has no method whose
signature would even ACCEPT a provider/model/temperature argument to
misuse. AgentRuntime.run() (runtime.py) is the only thing that calls
PromptBuilder.build() and AIGateway.complete() - see that module's own
docstring for the full orchestration.

This is a considered deviation from the single-method sketch in the
originally-approved architecture text, made specifically to satisfy the
refinement's own stated acceptance test ("integrate cleanly without
increasing coupling or violating the existing layer boundaries") more
rigorously than a single method could. Flagged explicitly here, and in
the implementation report, so this can be confirmed against intent
rather than silently assumed.
"""
import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from app.ai_gateway.request import GatewayResponse, TokenUsage
from app.prompt_builder.base import PromptContext


class AgentOutcome(str, enum.Enum):
    """M7.2 shipped SUCCESS/FAILURE only, deliberately smaller than
    app.workflow_engine.actions.base's own ActionOutcome
    (SUCCESS/FAILURE/RETRY/PENDING) - M7.2 had no long-running,
    multi-turn, or supervisor/multi-agent execution yet, so RETRY/PENDING
    would have been meaningless states no Agent could legitimately
    return.

    RETRY is added here in M7.3, exactly the "small, scoped addition"
    the M7.2 docstring anticipated - not a redesign. It means "the same
    agent should be tried again with the SAME AgentInput" (e.g.
    interpret() decided a model's answer was malformed or incomplete) -
    handled entirely inside AgentRuntime.run()'s own bounded retry loop
    (see runtime.py), never surfaced to a Supervisor. A Supervisor never
    sees AgentOutcome.RETRY on a completed step - AgentRuntime either
    resolves it into a real SUCCESS/FAILURE within
    settings.AGENT_RUNTIME_MAX_ATTEMPTS, or gives up and reports FAILURE.
    This is a private concern between AgentRuntime and the one agent it
    is running - it is NOT how Supervisor-level retry works
    (Supervisor-level "try this differently" is just a ordinary future
    decision reading a FAILED step from history, see
    app.supervisor.base's own docstring).

    PENDING is still not added - nothing in this codebase yet has a
    within-agent notion of "pause and resume mid-interpretation"; the
    plan-level equivalent is the Supervisor's own WAIT decision, one
    layer up, not an AgentOutcome value."""

    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"


@dataclass(frozen=True)
class AgentInput:
    """`context` is opaque, caller-supplied business input - e.g. a
    future Workflow Action would pass through its own ActionInput.context
    here unread, exactly the same opacity discipline ActionInput.context
    itself already applies one layer down. Only the Agent's own
    build_context() implementation gives this dict meaning.

    `premium_approved` (M11, AI Provider Hierarchy) is DELIBERATELY here,
    not inside `context` - it's a provider/approval concern, the one
    thing an Agent's build_context() must never see or touch (see
    Agent.build_context()'s own docstring). AgentRuntime.run_with_metadata()
    is the only reader - it copies this onto the GatewayRequest it builds,
    after PromptBuilder.build() has already run, exactly like it already
    keeps model/temperature/etc. out of an Agent's reach."""

    context: dict
    idempotency_key: str | None = None
    premium_approved: bool = False


@dataclass(frozen=True)
class AgentOutput:
    """`result` mirrors ActionOutput.result's own shape/purpose one layer
    down - opaque JSONB, meaningful only to whichever caller invoked this
    Agent. `error` populated only for FAILURE."""

    status: AgentOutcome
    result: dict | None = None
    error: str | None = None


@dataclass(frozen=True)
class PremiumApprovalContext:
    """M11 (AI Provider Hierarchy) addition. Populated on AgentExecutionResult
    only when AIGateway.complete() raised PremiumApprovalRequiredError - see
    that error's own docstring and app.ai_gateway.client's module docstring
    for the full "STOP, ask user" flow this surfaces. Carries exactly what
    a caller needs to render the approval prompt without re-deriving it."""

    candidate_provider_key: str
    estimated_cost_usd: float | None
    reasons: list[str]


@dataclass(frozen=True)
class AgentExecutionResult:
    """M7.3 addition. Wraps AgentOutput with observability metadata
    AgentRuntime already has in hand internally but M7.2's run() -
    unchanged, see runtime.py - discards after calling agent.interpret().
    Exists specifically to answer Supervisor-level explainability's
    "why was a provider changed" question (see
    app.supervisor.base.AgentStepResult, which is built directly from
    this) - without widening AgentOutput itself, which stays exactly
    the small, opaque, caller-facing shape it was in M7.2.
    provider_key/model/usage are None only when the call failed before
    a real GatewayResponse was ever produced (the whole provider chain
    exhausted - see AIGateway.complete()'s own docstring).

    `premium_approval` (M11) is populated ONLY when the Gateway call
    stopped specifically because a premium provider needs explicit user
    approval - a distinct, non-error outcome from an ordinary FAILURE
    (`output.status` is still AgentOutcome.FAILURE in this case, since
    M7.2's AgentOutcome vocabulary has no dedicated "awaiting approval"
    member - see that enum's own docstring for why PENDING was
    deliberately never added; this field is the additive, backward-
    compatible way to distinguish the two without widening AgentOutcome
    itself). Callers that care (e.g. LLMAnalysisEngine) check this field
    before treating a FAILURE as a genuine, terminal failure."""

    output: AgentOutput
    provider_key: str | None = None
    model: str | None = None
    usage: TokenUsage | None = None
    premium_approval: PremiumApprovalContext | None = None


class Agent(ABC):
    key: ClassVar[str]

    @abstractmethod
    def build_context(self, input_data: AgentInput) -> PromptContext:
        """Contribute business content ONLY. Must never reference a
        provider name, model id, temperature, token limit, timeout,
        budget, or response_format - none of those are reachable from
        this method's signature. Returns a PromptContext; AgentRuntime
        passes it, together with this Agent's resolved ExecutionPolicy,
        to PromptBuilder.build()."""
        raise NotImplementedError

    @abstractmethod
    def interpret(self, response: GatewayResponse, input_data: AgentInput) -> AgentOutput:
        """Translate a raw GatewayResponse (provider-agnostic, but still
        shaped like "a model's answer") into this Agent's own AgentOutput
        vocabulary. This is where an Agent decides whether the response
        actually satisfies its task (e.g. parsing/validating structured
        content), not merely relays it."""
        raise NotImplementedError
