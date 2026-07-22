"""
Built-in Workflow Definition bootstrap - M7.1 Part 2. Activates every
platform-authored WorkflowDefinition this application ships with,
on startup, through the SAME governed draft -> activate lifecycle
anything else uses (app.workflow_engine.definitions) - there is no
separate, unsanctioned way built-in workflows get created, and no manual
database edit is ever involved.

Deliberately a top-level module (app/workflow_bootstrap.py), not inside
app/workflow_engine/ - this is composition-root/application-wiring code
("which workflows does this deployment ship with"), not engine
machinery, matching the same reasoning app/workflow_actions/__init__.py
gives for its own placement. The engine itself never imports this
module.

BUILTIN_WORKFLOW_DEFINITIONS is the configuration surface this whole
module exists to serve: a plain, declarative Python list, appended to -
never a YAML/JSON file - because "adding X is a code change, not a
migration or a config file" is this codebase's existing convention for
every other pluggable surface (PROVIDER_REGISTRY, REPLY_CLASSIFIER_REGISTRY,
ACTION_REGISTRY). A step_graph is nested, non-trivial JSON already
carrying real semantics (action_key references, transition rules) - a
Python list of typed entries gets IDE/type-checking support an external
config file wouldn't, for a total ongoing maintenance cost of "append one
entry," which is exactly what "configuration-driven, extend without
touching startup logic" means in practice here. M7.1 Part 2 shipped with
one entry (the pilot); M8.8 appended a second (Discovery search
execution); future milestones add more the same way, never by modifying
activate_builtin_workflows() or app/main.py's own startup call.

activate_builtin_workflows() is deliberately ADDITIVE-ONLY: if a key
already has an ACTIVE version, it is left untouched - this function
NEVER auto-publishes a new version of an already-active built-in, even
if this module's own step_graph for that key has since changed in code.
Automatically re-publishing on every boot would be a form of automatic,
engine-driven workflow evolution the approved Compatibility Policy
explicitly forbids in spirit (definitions change only via a deliberate,
explicit authoring action) - shipping a genuinely new version of a
built-in workflow is a future, deliberate operation (e.g. a small admin
action or CLI), not something that happens silently as a side effect of
restarting the backend.
"""
import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.workflow_engine.definitions import activate_definition, create_draft_definition, resolve_active_definition

logger = logging.getLogger("sales_agent.workflow_bootstrap")


@dataclass(frozen=True)
class BuiltinWorkflowDefinition:
    """One entry in BUILTIN_WORKFLOW_DEFINITIONS below - the declarative
    shape activate_builtin_workflows() consumes. Mirrors
    create_draft_definition()'s own keyword arguments exactly (see
    app.workflow_engine.definitions) so adding an entry here never needs
    a parallel translation step."""

    key: str
    trigger_event_type: str
    step_graph: dict
    trigger_filter: dict | None = field(default=None)


def _pilot_conversation_created_workflow() -> BuiltinWorkflowDefinition:
    """M7.1 Part 2's pilot: conversation.created -> one step
    (workflow.record_execution) -> complete. Imported lazily from inside
    this function, not at module level - see BUILTIN_WORKFLOW_DEFINITIONS'
    own comment for why the action_key reference below is just an opaque
    string, never an import of app.workflow_actions itself (this module
    never needs to know the action's implementation, only its key)."""
    from app.workflow_actions.record_execution_action import RECORD_EXECUTION_ACTION_KEY

    return BuiltinWorkflowDefinition(
        key="conversation_created_pilot",
        trigger_event_type="conversation.created",
        step_graph={
            "start_step_id": "record_execution",
            "steps": {
                "record_execution": {
                    "action_key": RECORD_EXECUTION_ACTION_KEY,
                    "transitions": {"success": None, "failure": None},
                    "max_attempts": 1,
                }
            },
        },
    )


def _discovery_search_execution_workflow() -> BuiltinWorkflowDefinition:
    """M8.8: Live AI Workflow Visualization's first real (non-pilot)
    built-in - one step, exactly the pilot's own shape, deliberately not
    a richer multi-step graph. Per-provider granularity (the "current
    stage / completed / running / pending" detail the Live Workflow
    Visualization actually renders) comes from real domain Events published
    from INSIDE DiscoveryExecutionAction's single step (see
    app.discovery.pipeline's DISCOVERY_JOB_PROGRESS_EVENT_TYPE), not from
    modeling each provider as its own WorkflowStepInvocation - the engine
    only ever sees "one step, execute the search, report success/failure,"
    identical in shape to conversation_created_pilot above."""
    from app.workflow_actions.discovery_execution_action import DISCOVERY_EXECUTION_ACTION_KEY
    from app.discovery.pipeline import DISCOVERY_SEARCH_RUN_REQUESTED_EVENT_TYPE

    return BuiltinWorkflowDefinition(
        key="discovery_search_execution",
        trigger_event_type=DISCOVERY_SEARCH_RUN_REQUESTED_EVENT_TYPE,
        step_graph={
            "start_step_id": "execute_search",
            "steps": {
                "execute_search": {
                    "action_key": DISCOVERY_EXECUTION_ACTION_KEY,
                    "transitions": {"success": None, "failure": None},
                    "max_attempts": 1,
                }
            },
        },
    )


def _research_request_execution_workflow() -> BuiltinWorkflowDefinition:
    """M8.10: exact structural mirror of
    _discovery_search_execution_workflow above - one step, per-provider
    granularity comes from real domain Events published inside
    ResearchExecutionAction's single step, not from step_graph modeling."""
    from app.workflow_actions.research_execution_action import RESEARCH_EXECUTION_ACTION_KEY
    from app.research.pipeline import RESEARCH_REQUEST_RUN_REQUESTED_EVENT_TYPE

    return BuiltinWorkflowDefinition(
        key="research_request_execution",
        trigger_event_type=RESEARCH_REQUEST_RUN_REQUESTED_EVENT_TYPE,
        step_graph={
            "start_step_id": "execute_request",
            "steps": {
                "execute_request": {
                    "action_key": RESEARCH_EXECUTION_ACTION_KEY,
                    "transitions": {"success": None, "failure": None},
                    "max_attempts": 1,
                }
            },
        },
    )


# The configuration surface - see this module's own docstring. Built
# lazily (a list of zero-arg callables, not the resolved
# BuiltinWorkflowDefinition instances themselves) purely so importing
# THIS module never has a hard import-time dependency on
# app.workflow_actions - that import only actually happens inside
# activate_builtin_workflows(), at the point it's genuinely needed.
BUILTIN_WORKFLOW_DEFINITIONS: list = [
    _pilot_conversation_created_workflow,
    _discovery_search_execution_workflow,
    _research_request_execution_workflow,
]


def activate_builtin_workflows(db: Session) -> None:
    """Idempotent, safe to call on every startup. For each entry in
    BUILTIN_WORKFLOW_DEFINITIONS: no-op if a key already has an ACTIVE
    version (see this module's own docstring for why); otherwise
    authors a DRAFT and activates it through the normal governed
    lifecycle. Imports app.workflow_actions first - the one place this
    project guarantees every built-in workflow's referenced action_keys
    are registered before activate_definition()'s own step_graph
    validation runs."""
    import app.workflow_actions  # noqa: F401  (registers every action this package owns)

    for builtin_factory in BUILTIN_WORKFLOW_DEFINITIONS:
        builtin = builtin_factory()

        existing_active = resolve_active_definition(db, key=builtin.key)
        if existing_active is not None:
            logger.info(
                "Built-in workflow '%s' already ACTIVE (v%d) - skipping", builtin.key, existing_active.version
            )
            continue

        draft = create_draft_definition(
            db,
            key=builtin.key,
            trigger_event_type=builtin.trigger_event_type,
            step_graph=builtin.step_graph,
            trigger_filter=builtin.trigger_filter,
        )
        activated = activate_definition(db, draft)
        logger.info("Activated built-in workflow '%s' v%d (trigger_event_type=%s)", builtin.key, activated.version, builtin.trigger_event_type)
