"""
Step Runner worker - M7.1 Part 1, Phase 5, the second of the Workflow
Engine's two dedicated workers (see docs/architecture/
m7-workflow-engine-plan.md section 5 for the full "why two workers, not
one" reasoning, and event_dispatcher_worker.py's own docstring for the
other half of this split). Claims RUNNING WorkflowInstances, invokes the
registered Action for each instance's `current_step_id`, records one
append-only WorkflowStepInvocation row per attempt, and advances/pauses/
completes/fails the instance according to that step's `transitions` rule
and `max_attempts` bound.

This worker is the ONLY code path that ever invokes an Action, and the
ONLY code path that ever advances WorkflowInstance.current_step_id - the
Event Dispatcher (Phase 4) creates instances and resumes WAITING ones,
but never touches current_step_id itself and never calls
action.execute(). The two workers interact ONLY through shared database
state on WorkflowInstance.status/current_step_id/context - no direct
call, no queue, no RPC between them.

Claim strategy - one query does double duty (claims fresh RUNNING
instances AND reclaims stale ones in the same SELECT...FOR UPDATE SKIP
LOCKED), a deliberate simplification of the Delivery worker's own
two-function split (claim_next_batch + a separate periodic
reclaim_stale_claims - see app/delivery/worker.py). That split exists
there because DeliveryQueueItemStatus has a dedicated SENDING state
distinct from SCHEDULED; WorkflowInstanceStatus has no equivalent
"claimed" status of its own - RUNNING is both "eligible to be claimed"
and "currently claimed," disambiguated only by the claimed_by/claimed_at
columns - so one WHERE clause (`claimed_at IS NULL OR claimed_at <
stale_cutoff`) captures both cases without needing a second query or a
periodic sweep.

An instance that finishes one attempt this tick (success, definitive
failure, or retries-remaining) has its claim released (claimed_by/
claimed_at reset to NULL) before commit - so a still-RUNNING instance
with more work to do (advanced to a new current_step_id) is immediately
eligible for the very next tick's claim query, not stuck waiting out the
stale-claim window. An instance that crashes this worker process
mid-attempt (an unhandled exception outside process_instance's own
try/except - see run_one_tick) is NOT explicitly recovered inline;
exactly like Delivery's own documented precedent, it simply stays
claimed until WORKFLOW_STEP_RUNNER_STALE_CLAIM_MINUTES passes, at which
point the claim query's own staleness clause reclaims it - no separate
recovery code path is needed.

Same third-process-entrypoint mapper-registration requirement as every
other standalone worker in this codebase - `from app.db import base as
_base` below is required, not optional decoration.
"""
import logging
import time as time_module
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import base as _base  # noqa: F401  (imports every model so relationship() string refs resolve - see module docstring)
from app.db.session import SessionLocal
from app.models.enums import WorkflowInstanceStatus, WorkflowStepInvocationStatus
from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step_invocation import WorkflowStepInvocation
from app.workflow_engine.actions.base import ActionInput, ActionOutcome, ActionOutput
from app.workflow_engine.actions.registry import get_action

logger = logging.getLogger("sales_agent.workflow_step_runner_worker")

# One id per process, used to populate claimed_by purely for
# observability/debugging (which replica holds a claim) - never read back
# by any decision logic in this worker; the claim query only ever checks
# claimed_at.
_WORKER_ID = f"step-runner-{uuid.uuid4()}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _idempotency_key(instance_id: uuid.UUID, step_id: str) -> str:
    """Deliberately attempt-INDEPENDENT (see ActionInput's own docstring
    for why) - a retried invocation of the same step reuses this exact
    string."""
    return f"{instance_id}:{step_id}"


def claim_next_batch(db: Session, limit: int, now: datetime) -> list[WorkflowInstance]:
    """Claims (SELECT...FOR UPDATE SKIP LOCKED, stamps claimed_by/
    claimed_at) up to `limit` RUNNING instances not currently claimed (or
    whose claim has gone stale), oldest-updated-first. Must run inside a
    transaction the caller controls - this function flushes but does not
    commit, matching FIFOSchedulingPolicy.claim_next_batch's own
    contract (see app/delivery/scheduler/policy.py)."""
    stale_cutoff = now - timedelta(minutes=settings.WORKFLOW_STEP_RUNNER_STALE_CLAIM_MINUTES)
    stmt = (
        select(WorkflowInstance)
        .where(
            WorkflowInstance.status == WorkflowInstanceStatus.RUNNING,
            or_(WorkflowInstance.claimed_at.is_(None), WorkflowInstance.claimed_at < stale_cutoff),
        )
        .order_by(WorkflowInstance.updated_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    instances = list(db.scalars(stmt).all())
    for instance in instances:
        instance.claimed_by = _WORKER_ID
        instance.claimed_at = now
    db.flush()
    return instances


def _release_claim(instance: WorkflowInstance) -> None:
    instance.claimed_by = None
    instance.claimed_at = None


def _apply_transition(instance: WorkflowInstance, next_step_id: str | None, *, terminal_status: WorkflowInstanceStatus) -> None:
    """Shared by both the success and (definitive) failure branches -
    `next_step_id=None` means this branch of the step_graph intentionally
    ends here (validate_step_graph() at activation time already confirmed
    every non-null transition target exists in the graph - see
    definitions.py), so the instance reaches a terminal state;
    `next_step_id` set advances current_step_id and leaves the instance
    RUNNING, ready for this same worker's next tick."""
    if next_step_id is None:
        instance.status = terminal_status
        instance.completed_at = _now()
    else:
        instance.current_step_id = next_step_id
        instance.status = WorkflowInstanceStatus.RUNNING


def process_instance(db: Session, instance: WorkflowInstance) -> None:
    """Runs exactly ONE step-invocation attempt for `instance`'s current
    step - never loops internally to chase multiple steps in a single
    call, even if a step's transition immediately makes the instance
    eligible again - matching this codebase's "one bounded unit of work
    per claimed item per tick" discipline elsewhere. One commit for the
    whole attempt, same discipline as the Event Dispatcher's own
    process_one_event."""
    definition = db.get(WorkflowDefinition, instance.workflow_definition_id)
    if definition is None:
        # Defensive only - the FK is ondelete="RESTRICT" specifically so
        # this can never actually happen; release the claim so nothing
        # replicates a bad state and move on.
        _release_claim(instance)
        db.commit()
        logger.error("WorkflowInstance %s: pinned WorkflowDefinition %s no longer exists", instance.id, instance.workflow_definition_id)
        return

    step_def = definition.step_graph.get("steps", {}).get(instance.current_step_id)
    if not isinstance(step_def, dict):
        # Defensive only - validate_step_graph() at activate_definition()
        # time already confirmed every step referenced by a transition
        # exists, and current_step_id is only ever set to start_step_id
        # or a validated transition target. If this is somehow still
        # reached, fail loudly rather than loop forever on a step that
        # doesn't exist.
        instance.status = WorkflowInstanceStatus.FAILED
        instance.completed_at = _now()
        _release_claim(instance)
        db.commit()
        logger.error(
            "WorkflowInstance %s: current_step_id %r not found in its pinned definition's step_graph",
            instance.id,
            instance.current_step_id,
        )
        return

    action_key = step_def["action_key"]
    max_attempts = step_def.get("max_attempts", 1)
    transitions = step_def.get("transitions", {}) or {}

    prior_attempts = db.scalar(
        select(func.count())
        .select_from(WorkflowStepInvocation)
        .where(
            WorkflowStepInvocation.workflow_instance_id == instance.id,
            WorkflowStepInvocation.step_id == instance.current_step_id,
        )
    )
    attempt_number = (prior_attempts or 0) + 1

    action = get_action(action_key)
    action_input = ActionInput(
        workflow_instance_id=instance.id,
        step_id=instance.current_step_id,
        context=instance.context,
        idempotency_key=_idempotency_key(instance.id, instance.current_step_id),
        # M7.4: same step_def.get("action_config") the Event Dispatcher
        # already reads directly (event_dispatcher_worker.py) - now also
        # threaded through to the Action itself, so a step's own
        # action_config is no longer only readable by this worker.
        action_config=step_def.get("action_config") or {},
    )

    invocation = WorkflowStepInvocation(
        workflow_instance_id=instance.id,
        step_id=instance.current_step_id,
        action_key=action_key,
        attempt_number=attempt_number,
        status=WorkflowStepInvocationStatus.RUNNING,
        input_snapshot=instance.context,
        started_at=_now(),
    )
    db.add(invocation)
    db.flush()

    try:
        output = action.execute(action_input)
    except Exception as exc:  # noqa: BLE001 - a raising Action is treated as a FAILURE outcome, not a worker crash
        logger.exception("Action %r raised for WorkflowInstance %s step %s", action_key, instance.id, instance.current_step_id)
        output = ActionOutput(status=ActionOutcome.FAILURE, error=str(exc))

    invocation.completed_at = _now()

    if output.result:
        # Plain shallow merge, opaque pass-through - see ActionOutput's
        # own docstring. The engine's one reserved key, _woken_by_event,
        # is nulled back out this same way by WaitForEventAction's own
        # result on the attempt that consumes it - see
        # actions/wait_for_event.py.
        instance.context = {**instance.context, **output.result}

    if output.status == ActionOutcome.SUCCESS:
        invocation.status = WorkflowStepInvocationStatus.SUCCEEDED
        invocation.output = output.result
        _apply_transition(instance, transitions.get("success"), terminal_status=WorkflowInstanceStatus.COMPLETED)

    elif output.status == ActionOutcome.FAILURE:
        # A definitive failure - follows transitions.failure immediately,
        # regardless of remaining attempts. Only RETRY (below) consumes
        # the attempt budget.
        invocation.status = WorkflowStepInvocationStatus.FAILED
        invocation.error = output.error
        _apply_transition(instance, transitions.get("failure"), terminal_status=WorkflowInstanceStatus.FAILED)

    elif output.status == ActionOutcome.RETRY:
        invocation.status = WorkflowStepInvocationStatus.FAILED
        invocation.error = output.error
        if attempt_number < max_attempts:
            # Stays on the SAME current_step_id - a new attempt (with an
            # incremented attempt_number) happens next tick. This is what
            # "RETRY is handled internally by the Step Runner's
            # attempt-count loop, not a graph edge" (approved
            # architecture) means in code.
            instance.status = WorkflowInstanceStatus.RUNNING
        else:
            # Attempts exhausted - retry exhaustion follows the SAME
            # transitions.failure rule a definitive FAILURE would.
            _apply_transition(instance, transitions.get("failure"), terminal_status=WorkflowInstanceStatus.FAILED)

    elif output.status == ActionOutcome.PENDING:
        # The built-in wait-for-event pseudo-action's normal "nothing has
        # happened yet" outcome (also usable by any future long-running
        # domain Action) - current_step_id is left unchanged; the Event
        # Dispatcher worker is what resumes this instance later. This
        # attempt's invocation row is intentionally not a failure.
        invocation.status = WorkflowStepInvocationStatus.PENDING
        instance.status = WorkflowInstanceStatus.WAITING

    else:  # pragma: no cover - defensive only, no Action in this codebase can produce this
        invocation.status = WorkflowStepInvocationStatus.FAILED
        invocation.error = f"Unknown ActionOutcome: {output.status!r}"
        _apply_transition(instance, transitions.get("failure"), terminal_status=WorkflowInstanceStatus.FAILED)

    _release_claim(instance)
    db.commit()


def run_one_tick() -> int:
    """Claims and processes one batch. Returns the number of instances
    processed, so the caller (the loop, or a test) can log/assert on
    it."""
    db = SessionLocal()
    try:
        claimed = claim_next_batch(db, settings.WORKFLOW_STEP_RUNNER_BATCH_SIZE, _now())
        db.commit()
        claimed_ids = [instance.id for instance in claimed]
    finally:
        db.close()

    for instance_id in claimed_ids:
        # Fresh session per instance - one instance's failure must never
        # poison the transaction state for the next one in the batch,
        # same discipline as every other worker loop in this codebase.
        db = SessionLocal()
        try:
            instance = db.get(WorkflowInstance, instance_id)
            if instance is not None:
                process_instance(db, instance)
        except Exception:  # noqa: BLE001 - the worker loop must survive one bad instance
            logger.exception("Unhandled error processing WorkflowInstance %s", instance_id)
            db.rollback()
            # Deliberately NOT recovered inline here - see this module's
            # own docstring for why leaving the claim in place until
            # WORKFLOW_STEP_RUNNER_STALE_CLAIM_MINUTES elapses is the
            # correct, sufficient recovery path, matching Delivery's own
            # documented precedent.
        finally:
            db.close()

    return len(claimed_ids)


def run_forever() -> None:  # pragma: no cover - the loop itself isn't unit-testable
    logger.info(
        "Workflow Step Runner starting - poll_interval=%ss batch_size=%s stale_claim_minutes=%s",
        settings.WORKFLOW_STEP_RUNNER_POLL_INTERVAL_SECONDS,
        settings.WORKFLOW_STEP_RUNNER_BATCH_SIZE,
        settings.WORKFLOW_STEP_RUNNER_STALE_CLAIM_MINUTES,
    )
    while True:
        try:
            processed = run_one_tick()
            if processed:
                logger.info("Workflow Step Runner tick: processed %d instance(s)", processed)
        except Exception:  # noqa: BLE001 - one bad tick must never kill the worker process
            logger.exception("Unhandled error in Workflow Step Runner tick")
        time_module.sleep(settings.WORKFLOW_STEP_RUNNER_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    # Deliberately unchanged from Part 1 - this module (and this
    # __main__ block) must NEVER import app.workflow_actions or any
    # other action-providing package, even for a real production
    # worker's own bootstrap needs; that would let app/workflow_engine/
    # import a sibling package by name, contradicting the exact boundary
    # this milestone's own architecture review draws (see
    # app/workflow_actions/__init__.py's own docstring: "This import is
    # deliberately NEVER made from anywhere inside app/workflow_engine/
    # itself"). The real production entrypoint that boots THIS worker is
    # app/run_step_runner_worker.py - a composition-root script that
    # lives outside app/workflow_engine/, imports app.workflow_actions
    # for its registration side effect, and then calls run_forever()
    # below. docker-compose.yml's workflow_step_runner_worker service
    # invokes that script, not this module, directly.
    logging.basicConfig(level=logging.INFO)
    run_forever()
