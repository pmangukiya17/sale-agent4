"""
Workflow Definition governance logic - Part 1, Phase 2. Implements the
approved Compatibility Policy (docs/architecture/m7-workflow-engine-plan.md
section 3) as enforced code, not just documented convention: every
function below that modifies a WorkflowDefinition row checks `status`
first and refuses if the row isn't in the state that operation requires.
There is no other sanctioned code path anywhere in this codebase that is
permitted to write to a WorkflowDefinition's status/step_graph/
trigger_event_type/trigger_filter columns.

step_graph shape (a plain JSON object, validated by validate_step_graph()
below, never enforced by the database):

    {
      "start_step_id": "<step id>",
      "steps": {
        "<step id>": {
          "action_key": "<registered action key>",
          "action_config": { ... opaque, optional, step-specific config },
          "transitions": {"success": "<step id or null>", "failure": "<step id or null>"},
          "max_attempts": <positive int, default 1>
        },
        ...
      }
    }

`transitions.success`/`transitions.failure` name the next step_id, or
null for a terminal outcome (null under "success" means the instance
COMPLETES; null under "failure" means the instance FAILS). There is no
"retry"/"pending" transition key - RETRY is handled internally by the
Step Runner's own attempt-count loop (Part 1, Phase 5), never a graph
edge; PENDING means "pause, become WAITING," also not a graph transition
- the instance simply stays on the same step until resumed.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import WorkflowDefinitionStatus
from app.models.workflow_definition import WorkflowDefinition
from app.workflow_engine.actions.registry import is_action_registered

_VALID_TRANSITION_KEYS = {"success", "failure"}


def validate_step_graph(step_graph: dict) -> list[str]:
    """Returns a list of human-readable validation errors - empty means
    valid. Never raises on a malformed graph; malformed input just
    produces errors describing what's wrong, so a caller (e.g. a future
    admin tool) can show all problems at once rather than one at a time.
    Checks (Risk 4 from the approved architecture, the hard gate on
    DRAFT -> ACTIVE): start_step_id is set and refers to a real step,
    every action_key is registered, every transition target is either
    null or a real step, every step is reachable from the start step,
    and the graph contains no cycle."""
    errors: list[str] = []

    if not isinstance(step_graph, dict):
        return ["step_graph must be a JSON object"]

    start_step_id = step_graph.get("start_step_id")
    steps = step_graph.get("steps")

    if not start_step_id or not isinstance(start_step_id, str):
        errors.append("step_graph.start_step_id must be a non-empty string")

    if not isinstance(steps, dict) or not steps:
        errors.append("step_graph.steps must be a non-empty object")
        return errors  # nothing further can be validated without steps

    if start_step_id and start_step_id not in steps:
        errors.append(f"start_step_id '{start_step_id}' is not a key in steps")

    for step_id, step_def in steps.items():
        if not isinstance(step_def, dict):
            errors.append(f"step '{step_id}' must be a JSON object")
            continue

        action_key = step_def.get("action_key")
        if not action_key or not isinstance(action_key, str):
            errors.append(f"step '{step_id}' is missing a valid action_key")
        elif not is_action_registered(action_key):
            errors.append(f"step '{step_id}' references unknown action_key '{action_key}'")

        transitions = step_def.get("transitions", {})
        if not isinstance(transitions, dict):
            errors.append(f"step '{step_id}'.transitions must be a JSON object")
            transitions = {}
        for outcome_key, next_step_id in transitions.items():
            if outcome_key not in _VALID_TRANSITION_KEYS:
                errors.append(f"step '{step_id}' has an unknown transition key '{outcome_key}' (expected 'success' or 'failure')")
            if next_step_id is not None and next_step_id not in steps:
                errors.append(f"step '{step_id}' transitions '{outcome_key}' to unknown step '{next_step_id}'")

        max_attempts = step_def.get("max_attempts", 1)
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            errors.append(f"step '{step_id}'.max_attempts must be a positive integer")

    if start_step_id in steps:
        unreachable = _find_unreachable_steps(steps, start_step_id)
        if unreachable:
            errors.append(f"unreachable step(s): {sorted(unreachable)}")

        cycle = _find_cycle(steps, start_step_id)
        if cycle:
            errors.append(f"step graph contains a cycle: {' -> '.join(cycle)}")

    return errors


def _step_transitions(steps: dict, step_id: str) -> dict:
    step_def = steps.get(step_id)
    transitions = step_def.get("transitions") if isinstance(step_def, dict) else None
    return transitions if isinstance(transitions, dict) else {}


def _find_unreachable_steps(steps: dict, start_step_id: str) -> set[str]:
    reachable = {start_step_id}
    frontier = [start_step_id]
    while frontier:
        current = frontier.pop()
        for next_step_id in _step_transitions(steps, current).values():
            if next_step_id and next_step_id in steps and next_step_id not in reachable:
                reachable.add(next_step_id)
                frontier.append(next_step_id)
    return set(steps.keys()) - reachable


def _find_cycle(steps: dict, start_step_id: str) -> list[str] | None:
    visited: set[str] = set()
    stack: list[str] = []
    stack_set: set[str] = set()

    def dfs(node: str) -> list[str] | None:
        visited.add(node)
        stack.append(node)
        stack_set.add(node)
        for next_step_id in _step_transitions(steps, node).values():
            if not next_step_id or next_step_id not in steps:
                continue
            if next_step_id in stack_set:
                cycle_start = stack.index(next_step_id)
                return stack[cycle_start:] + [next_step_id]
            if next_step_id not in visited:
                result = dfs(next_step_id)
                if result:
                    return result
        stack.pop()
        stack_set.discard(node)
        return None

    return dfs(start_step_id)


def resolve_active_definition(db: Session, *, key: str) -> WorkflowDefinition | None:
    """Returns the platform-authored (company_profile_id IS NULL) ACTIVE
    WorkflowDefinition for `key`, or None if none is currently ACTIVE (a
    valid state - see WorkflowDefinitionStatus's own docstring). Business-
    authored resolution (scoped by company_profile_id) is explicitly out
    of scope for M7.1 - the architecture reserves the column, this
    function does not yet resolve against it."""
    return db.scalars(
        select(WorkflowDefinition).where(
            WorkflowDefinition.key == key,
            WorkflowDefinition.status == WorkflowDefinitionStatus.ACTIVE,
            WorkflowDefinition.company_profile_id.is_(None),
        )
    ).first()


def create_draft_definition(
    db: Session,
    *,
    key: str,
    trigger_event_type: str,
    step_graph: dict,
    trigger_filter: dict | None = None,
) -> WorkflowDefinition:
    """Creates a new DRAFT version for `key` - version is computed as
    MAX(version) + 1 for this key (1 if no version exists yet), never
    supplied by the caller, so two rows can never collide on version
    number even across concurrent authoring. Deliberately does NOT
    validate the step graph here - a DRAFT is allowed to be a genuine
    work in progress (Compatibility Policy: "DRAFT definitions may be
    modified until they are published"); validation is a hard gate only
    at activate_definition() time, below."""
    latest_version = db.scalar(select(func.max(WorkflowDefinition.version)).where(WorkflowDefinition.key == key))
    next_version = (latest_version or 0) + 1

    definition = WorkflowDefinition(
        key=key,
        version=next_version,
        status=WorkflowDefinitionStatus.DRAFT,
        trigger_event_type=trigger_event_type,
        trigger_filter=trigger_filter,
        step_graph=step_graph,
        company_profile_id=None,
    )
    db.add(definition)
    db.commit()
    db.refresh(definition)
    return definition


def update_draft_definition(
    db: Session,
    definition: WorkflowDefinition,
    *,
    step_graph: dict | None = None,
    trigger_event_type: str | None = None,
    trigger_filter: dict | None = None,
) -> WorkflowDefinition:
    """The only sanctioned way to edit a WorkflowDefinition's content -
    refuses unless `definition.status == DRAFT` (Compatibility Policy:
    "ACTIVE workflow definitions cannot be edited. DEPRECATED workflow
    definitions cannot be edited.")."""
    if definition.status != WorkflowDefinitionStatus.DRAFT:
        raise ValueError(
            f"cannot modify WorkflowDefinition '{definition.key}' v{definition.version}: "
            f"status is {definition.status.value}, not draft - only DRAFT definitions may be edited"
        )

    if step_graph is not None:
        definition.step_graph = step_graph
    if trigger_event_type is not None:
        definition.trigger_event_type = trigger_event_type
    if trigger_filter is not None:
        definition.trigger_filter = trigger_filter

    db.commit()
    db.refresh(definition)
    return definition


def activate_definition(db: Session, definition: WorkflowDefinition) -> WorkflowDefinition:
    """The ONLY sanctioned way to transition a WorkflowDefinition to
    ACTIVE. Atomically (a) validates the step graph (Risk 4's hard gate -
    raises if invalid, never activates a broken definition), (b) demotes
    whichever version of the same `key` was previously ACTIVE, if any,
    to DEPRECATED, and (c) activates `definition` (must currently be
    DRAFT) - all within one transaction, one final commit. This is
    definition-lifecycle bookkeeping performed once, at publish time, by
    a deliberate human/operator action - it is categorically different
    from "migrating a running instance," which never happens anywhere in
    this codebase: activating a new version only changes which version a
    FUTURE trigger event resolves to via resolve_active_definition()
    above; every already-running WorkflowInstance stays pinned to
    whatever version it started on, permanently (see WorkflowInstance's
    own docstring, Part 1 Phase 3).

    Demote-then-activate is enforced with an explicit intermediate
    db.flush() between the two status writes below, not merely by their
    Python statement order. uq_workflow_definitions_key_active (a
    partial unique index, WHERE status = 'active' - see migration 0014)
    is checked per-statement by Postgres, not deferred to commit, and
    Postgres partial indexes cannot be made DEFERRABLE at all (only
    constraints added via ADD CONSTRAINT can be - CREATE INDEX cannot).
    Relying on Python assignment order alone does not control SQL
    statement order: both assignments are ORM attribute writes that get
    batched into whatever single flush db.commit() triggers, and
    SQLAlchemy's unit-of-work does not guarantee UPDATE ordering between
    two dirty instances of the same mapped class with no FK/relationship
    dependency between them - that ordering is an unspecified
    implementation detail, not part of its documented contract, and can
    depend on incidental factors (e.g. each object's path into the
    session's identity map) that can vary between process runs even with
    an unchanged SQLAlchemy version. If the previously-ACTIVE row's own
    UPDATE has not yet reached the database at the moment `definition`'s
    UPDATE runs, the two rows are briefly both 'active' in the index's
    eyes and the unique index raises. The intermediate flush() below
    removes that ambiguity by forcing the demotion's UPDATE to actually
    execute before `definition`'s status is even set to ACTIVE in
    Python - there is no longer a single ambiguous flush containing both
    writes for the unit-of-work to reorder. The transaction itself is
    still one atomic unit: flush() sends pending SQL over the same open
    transaction/connection, it does not commit or release anything, so a
    failure after this point still rolls back the demotion together with
    everything else."""
    if definition.status != WorkflowDefinitionStatus.DRAFT:
        raise ValueError(
            f"cannot activate WorkflowDefinition '{definition.key}' v{definition.version}: "
            f"status is {definition.status.value}, not draft - only a DRAFT definition may be activated"
        )

    validation_errors = validate_step_graph(definition.step_graph)
    if validation_errors:
        raise ValueError(
            f"cannot activate WorkflowDefinition '{definition.key}' v{definition.version}: "
            f"step graph is invalid: {'; '.join(validation_errors)}"
        )

    previously_active = db.scalars(
        select(WorkflowDefinition).where(
            WorkflowDefinition.key == definition.key,
            WorkflowDefinition.status == WorkflowDefinitionStatus.ACTIVE,
        )
    ).first()
    if previously_active is not None:
        previously_active.status = WorkflowDefinitionStatus.DEPRECATED
        # Force this UPDATE to hit the database now, before `definition`
        # is even set to ACTIVE below - see the docstring above for why
        # Python statement order alone cannot guarantee this. Still the
        # same open transaction; only db.commit() further down actually
        # commits/releases it.
        db.flush()

    definition.status = WorkflowDefinitionStatus.ACTIVE
    db.commit()
    db.refresh(definition)
    return definition


def deprecate_definition(db: Session, definition: WorkflowDefinition) -> WorkflowDefinition:
    """Retires an ACTIVE definition WITHOUT activating a replacement -
    the key is then left with zero ACTIVE versions, a valid, supported
    state (Compatibility Policy) that pauses new-instance creation
    without requiring a replacement version to be ready."""
    if definition.status != WorkflowDefinitionStatus.ACTIVE:
        raise ValueError(
            f"cannot deprecate WorkflowDefinition '{definition.key}' v{definition.version}: "
            f"status is {definition.status.value}, not active"
        )
    definition.status = WorkflowDefinitionStatus.DEPRECATED
    db.commit()
    db.refresh(definition)
    return definition
