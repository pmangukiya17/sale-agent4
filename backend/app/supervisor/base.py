"""
Core Supervisor contract and data shapes - M7.3.

Everything here is a frozen dataclass, same discipline used throughout
app.ai_gateway/app.prompt_builder/app.ai_agents: no shared mutable state,
no hidden coupling. SupervisionState in particular is designed to be
fully JSON-serializable (no object references, no closures) SPECIFICALLY
so that persisting/resuming a suspended plan in a later milestone is
additive - a new table plus (de)serialization code - not a redesign of
this module. Persistence itself is explicitly NOT built in M7.3 (no
migration, no DB model) - only the shape is kept ready for it.

Decision vocabulary: a deliberately small, stable set of KINDS, each
carrying a typed, extensible payload - not a flat enum matched by a
growing if/elif chain. WAIT_FOR_HUMAN / WAIT_FOR_EVENT / WAIT_FOR_TIME /
REQUEST_APPROVAL are NOT four separate decision kinds: they are all
structurally "suspend this plan, to be resumed later by something
external," differing only in WHAT that something is - modeled here as
ONE WAIT kind carrying a typed ResumeTrigger payload. Adding a new
trigger type later (e.g. a webhook) is a new ResumeTriggerType value, not
a new decision kind SupervisorRuntime has to learn to dispatch.
ABORT is kept distinct from FAIL on purpose: FAIL means the plan pursued
its goal and could not reach it; ABORT means the plan is being
deliberately terminated for a reason unrelated to failure (a human
cancels a pending approval, or Plan Validation rejects a proposed
decision before it ever runs - see plan_validation.py).

Every decision-producing SupervisorDecision requires a `reason` string -
not optional metadata, a required field - and every agent invocation
requires `inputs_consumed`. This is what makes explainability an
enforced contract rather than a best-effort logging convention: the
question "why was this agent selected / why was another skipped / which
outputs were consumed by later agents" is answerable directly off the
decision object itself, for every decision, because the shape does not
allow constructing one without an answer.
"""
import enum
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import ClassVar

# TokenUsage is imported from app.ai_agents.base (which already binds it
# in its own namespace via its own `from app.ai_gateway.request import
# ..., TokenUsage`) rather than from app.ai_gateway.request directly -
# so app.supervisor's only AI-stack dependency edge is app.ai_agents,
# never app.ai_gateway or app.prompt_builder directly, even for a plain,
# inert data type. This keeps "app.supervisor never bypasses
# AgentRuntime" a literal, grep-checkable fact (`grep -rlE
# "from app\.(prompt_builder|ai_gateway)" app/supervisor/` returns
# nothing), not just true in spirit. app.ai_agents is the legitimate
# conduit here because this type is already part of AgentRuntime's own
# public vocabulary (AgentExecutionResult.usage) - not an arbitrary
# detour.
from app.ai_agents.base import AgentOutput, TokenUsage

SUPERVISION_STATE_SCHEMA_VERSION = 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionKind(str, enum.Enum):
    RUN_AGENTS = "run_agents"
    SKIP_AGENT = "skip_agent"
    WAIT = "wait"
    COMPLETE = "complete"
    FAIL = "fail"
    ABORT = "abort"


class ResumeTriggerType(str, enum.Enum):
    """Closed today, deliberately small - extend when a real future
    trigger type needs it (e.g. WEBHOOK). Each is a plain payload
    variant of the single WAIT decision kind, not a new decision kind -
    see module docstring."""

    EVENT = "event"
    TIME = "time"
    HUMAN_APPROVAL = "human_approval"


@dataclass(frozen=True)
class ResumeTrigger:
    """`payload` is intentionally opaque - same "dict bag, not a rigid
    schema" discipline as PromptContext.business_context. For EVENT: a
    future Workflow Action bridging a WAIT decision into the engine's own
    wait-for-event mechanism (app.workflow_engine.actions.wait_for_event)
    would read something like {"event_type": "..."}, mirroring that
    action's own action_config.event_type convention - not built in
    M7.3, named here so the shape is ready for it. For TIME: e.g.
    {"resume_at": "<ISO 8601 timestamp>"}. For HUMAN_APPROVAL: whatever
    describes whats being approved, e.g. {"approval_subject": "..."}."""

    type: ResumeTriggerType
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AgentInvocationRequest:
    """One agent to invoke, as part of a RUN_AGENTS decision.
    `inputs_consumed` names which prior SupervisionStep indices (see
    SupervisionStep.step_index below) contributed to `context` - REQUIRED
    (may be an empty tuple for a plan's first step, but must be
    explicitly stated, never omitted) so "which outputs were consumed by
    later agents" is always answerable directly off the request itself.
    Two AgentInvocationRequests inside the SAME RUN_AGENTS decision are,
    by construction, asserted to have no ordering dependency on each
    other - see plan_validation.py and runtime.py for the consequence of
    that assertion (SupervisorRuntime may run them concurrently)."""

    agent_key: str
    context: dict
    inputs_consumed: tuple[int, ...] = ()
    idempotency_key: str | None = None


@dataclass(frozen=True)
class SupervisorDecision:
    """Every field beyond `kind`/`reason` is populated only for the
    kind(s) noted - the classmethod constructors below are the
    sanctioned way to build one; using them makes it structurally hard
    to build a decision missing the field its own kind requires
    (plan_validation.py still checks this too, as defense in depth, since
    nothing stops a Supervisor implementation from constructing this
    dataclass directly)."""

    kind: DecisionKind
    reason: str
    agent_invocations: tuple[AgentInvocationRequest, ...] = ()  # RUN_AGENTS only
    skipped_agent_key: str | None = None  # SKIP_AGENT only
    resume_trigger: ResumeTrigger | None = None  # WAIT only
    result: dict | None = None  # COMPLETE only
    error: str | None = None  # FAIL / ABORT only

    @classmethod
    def run_agents(cls, *, reason: str, invocations: tuple[AgentInvocationRequest, ...]) -> "SupervisorDecision":
        return cls(kind=DecisionKind.RUN_AGENTS, reason=reason, agent_invocations=invocations)

    @classmethod
    def skip_agent(cls, *, reason: str, agent_key: str) -> "SupervisorDecision":
        return cls(kind=DecisionKind.SKIP_AGENT, reason=reason, skipped_agent_key=agent_key)

    @classmethod
    def wait(cls, *, reason: str, resume_trigger: ResumeTrigger) -> "SupervisorDecision":
        return cls(kind=DecisionKind.WAIT, reason=reason, resume_trigger=resume_trigger)

    @classmethod
    def complete(cls, *, reason: str, result: dict) -> "SupervisorDecision":
        return cls(kind=DecisionKind.COMPLETE, reason=reason, result=result)

    @classmethod
    def fail(cls, *, reason: str, error: str) -> "SupervisorDecision":
        return cls(kind=DecisionKind.FAIL, reason=reason, error=error)

    @classmethod
    def abort(cls, *, reason: str, error: str) -> "SupervisorDecision":
        return cls(kind=DecisionKind.ABORT, reason=reason, error=error)


@dataclass(frozen=True)
class AgentStepResult:
    """One agent's outcome within a RUN_AGENTS SupervisionStep - built
    directly from AgentRuntime.run_with_metadata()'s AgentExecutionResult
    (see app.ai_agents.base), which is exactly why that type exists:
    without it, provider_key/model/usage would not be available up here
    at all, and "why was a provider changed" would be unanswerable."""

    agent_key: str
    output: AgentOutput
    provider_key: str | None = None
    model: str | None = None
    usage: TokenUsage | None = None


@dataclass(frozen=True)
class SupervisionStep:
    """One immutable record of one decide_next() call and its
    consequence. `step_index` is this step's position in `history` -
    the same value AgentInvocationRequest.inputs_consumed and
    validation-error messages reference. `agent_results` is populated
    only for RUN_AGENTS steps, in actual completion order (not request
    order - see runtime.py's own docstring on why wall-clock order isn't
    guaranteed even though decision-level behavior is)."""

    step_index: int
    decision: SupervisorDecision
    agent_results: tuple[AgentStepResult, ...] = ()
    started_at: datetime = field(default_factory=_now)
    completed_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class SupervisionState:
    """The whole state of one Supervisor plan execution - immutable,
    append-only via with_step() below, never mutated in place. A
    Supervisor implementation's decide_next() receives one of these and
    must treat it as read-only; only SupervisorRuntime ever produces the
    next one.

    schema_version: the STRUCTURAL shape of SupervisionState/
    SupervisionStep itself (a serialization/technical concern) - a
    suspended plan may be read back by different code than wrote it
    (this is the first place in this codebase where that's a likely
    scenario, not a theoretical one, given plans may wait days). Bump
    SUPERVISION_STATE_SCHEMA_VERSION when this dataclass's own shape
    changes in a way that would break deserializing an older value.

    plan_version: which version of the registered Supervisor's own
    decide_next() LOGIC produced this state (a business/behavioral
    concern, distinct from schema_version) - mirrors
    WorkflowDefinition's own version field and its "already-running
    instances stay pinned to whatever version they started on" rule.
    Reserved here, not yet enforced anywhere - app.supervisor.registry
    has no versioning/governance lifecycle in M7.3 (SUPERVISOR_REGISTRY
    holds exactly one implementation per plan_key, same as
    AGENT_REGISTRY) - the field exists so a future governed registry can
    be added without migrating every already-persisted SupervisionState.

    execution_id: minted once, at start_supervision() below, immutable
    for the life of this plan execution. This is the PERSISTED half of
    execution identity (linking every SupervisionStep together for
    replay/audit) - the LOGGING-correlation half is a separate,
    contextvars-propagated concern, see observability.py; deliberately
    not the same mechanism, since replay needs durable structured state
    and debugging needs log correlation, and conflating them would mean
    every layer's request/response dataclasses would need a new field
    they don't otherwise conceptually own.
    """

    schema_version: int
    plan_key: str
    plan_version: int
    execution_id: uuid.UUID
    initial_context: dict
    history: tuple[SupervisionStep, ...] = ()
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    @classmethod
    def start(cls, *, plan_key: str, initial_context: dict, plan_version: int = 1) -> "SupervisionState":
        now = _now()
        return cls(
            schema_version=SUPERVISION_STATE_SCHEMA_VERSION,
            plan_key=plan_key,
            plan_version=plan_version,
            execution_id=uuid.uuid4(),
            initial_context=initial_context,
            history=(),
            created_at=now,
            updated_at=now,
        )

    def with_step(self, step: SupervisionStep) -> "SupervisionState":
        return replace(self, history=self.history + (step,), updated_at=_now())


class Supervisor(ABC):
    """`allowed_agent_keys` is a REQUIRED declared allowlist, not an
    afterthought - every plan states upfront which agent_keys it may
    legally invoke, checked by plan_validation.py against every
    RUN_AGENTS decision this Supervisor emits, regardless of whether
    that decision came from deterministic code or was derived from an
    LLM-driven Planning Agent's own output. This is the concrete guard
    against a hallucinated or prompt-injected plan naming some unrelated
    agent_key that happens to exist in AGENT_REGISTRY for a totally
    different plan."""

    key: ClassVar[str]
    allowed_agent_keys: ClassVar[frozenset[str]]

    @abstractmethod
    def decide_next(self, state: SupervisionState) -> SupervisorDecision:
        """Read `state.history`, return exactly one decision. Must never
        reference AgentRuntime, AIGateway, PromptBuilder, or an Agent
        instance - nothing in this method's reachable signature permits
        it. See package docstring for why that is enforced by
        construction, not convention."""
        raise NotImplementedError
