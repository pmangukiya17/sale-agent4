"""
The Action contract - the ONLY shape a workflow step's real work takes,
per the approved architecture (docs/architecture/m7-workflow-engine-
plan.md section 6). Every field on ActionInput/ActionOutput below is
deliberately opaque to the engine: domain modules give `context`,
`result`, and `error` their entire meaning; the engine only ever passes
them through, unread.

Part of Part 1, Phase 2 (folded in here, not a separately-named phase in
the current implementation batch, because
app.workflow_engine.definitions.validate_step_graph() - also Phase 2 -
needs a real registry to check a step's action_key against; see that
module's own docstring for the full reasoning).
"""
import enum
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# The engine's own reserved, built-in pseudo-action key (Part 1, Phase
# 5) - a step configured with this action_key doesn't invoke any domain
# code; it declares "pause and wait for an event matching
# action_config.event_type." Defined here, in the shared contract
# module, rather than in the worker files that use it
# (event_dispatcher_worker.py, step_runner_worker.py, and the
# wait_for_event Action implementation itself), so none of those three
# modules needs to import from one another to agree on this literal
# string - the exact "no wrong-direction import" discipline this
# package's own docstring establishes, applied here to avoid an
# unnecessary cross-worker dependency too.
WAIT_FOR_EVENT_ACTION_KEY = "engine.wait_for_event"


class ActionOutcome(str, enum.Enum):
    """The Action's own return-value vocabulary - deliberately NOT the
    same enum as WorkflowStepInvocationStatus (Part 1, Phase 3), which
    describes a persisted row's broader lifecycle (including RUNNING/
    SKIPPED, states an Action itself never returns). The Step Runner
    (Part 1, Phase 5) is what translates an ActionOutcome into a
    WorkflowStepInvocationStatus - keeping the two vocabularies distinct
    is deliberate: an Action's contract should never need to know how
    the engine records its own execution history.

    Not a database column (unlike every enum in app.models.enums) - this
    value is never persisted as this exact type; the Step Runner reads
    it in-process and translates it before writing anything to the
    database. That is why it lives here, in the engine's own package,
    rather than in app/models/enums.py alongside every persisted enum.
    """

    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"
    PENDING = "pending"


@dataclass(frozen=True)
class ActionInput:
    """workflow_instance_id/step_id identify which step is executing.
    `context` is the instance's own accumulated, opaque JSONB working
    data, passed through by the engine, never validated or interpreted
    by it. `idempotency_key` is deliberately ATTEMPT-INDEPENDENT (derived
    from workflow_instance_id + step_id only, never attempt_number - see
    app.workflow_engine.step_runner_worker, Part 1 Phase 5) so a retried
    invocation reuses the same key and an Action implementation can
    recognize its own prior attempt, avoiding a duplicate side effect.

    `action_config` - M7.4 addition, additive and backward-compatible
    (defaults to an empty dict, so every pre-M7.4 direct construction of
    ActionInput, in this codebase's own tests included, remains valid
    unmodified). This is the SAME per-step `action_config` object the
    step_graph schema has always supported (see
    app.workflow_engine.definitions's own step_graph docstring,
    `"action_config": { ... opaque, optional, step-specific config }`)
    and which event_dispatcher_worker.py already reads directly off
    step_def for the engine's own built-in wait-for-event pseudo-action
    - this field simply exposes that SAME already-existing concept to an
    Action's own execute() method too, which had no way to read it
    before M7.4 (only step_runner_worker.py, which owns step_def, could
    see it). Populated by step_runner_worker.py's process_instance() from
    `step_def.get("action_config") or {}` - see that function's own
    ActionInput construction. Opaque to the engine, exactly like
    `context` - only a concrete Action's own execute() gives it meaning
    (e.g. SupervisorInvocationAction reads action_config["plan_key"] -
    see app/workflow_actions/supervisor_invocation_action.py)."""

    workflow_instance_id: uuid.UUID
    step_id: str
    context: dict
    idempotency_key: str
    action_config: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ActionOutput:
    """`result` is merged back into the instance's own context by the
    Step Runner - opaque JSONB, meaningful only to whichever later step
    reads it. `error` is populated only for FAILURE/RETRY, stored
    verbatim on the resulting workflow_step_invocations row for
    debugging/explainability - never interpreted by the engine beyond
    storing it."""

    status: ActionOutcome
    result: dict | None = None
    error: str | None = None


class Action(ABC):
    """One method, deliberately - see architecture section 6. Whether a
    concrete implementation's execute() makes a network call, queries the
    database, calls an LLM, or does nothing but return a fixed value
    (the engine's own built-in wait-for-event pseudo-action, Part 1
    Phase 5) is entirely its own concern, invisible to this contract."""

    @abstractmethod
    def execute(self, input_data: ActionInput) -> ActionOutput:
        raise NotImplementedError
