"""
Event Dispatcher worker - M7.1 Part 1, Phase 4, one of the Workflow
Engine's two dedicated workers (see docs/architecture/
m7-workflow-engine-plan.md section 5 for the full "why two workers, not
one" reasoning). Matches published Events against ACTIVE
WorkflowDefinitions (starting new WorkflowInstances, pinned to the exact
version that matched) and against WAITING WorkflowInstances (resuming
them). Never invokes an Action - that is exclusively the Step Runner
worker's job (event_dispatcher_worker.py and step_runner_worker.py are
both Part 1 of this milestone, but strictly independent processes with
no direct call, no queue, no RPC between them; they interact ONLY
through shared database state on WorkflowInstance.status - the
Dispatcher writes RUNNING, the Runner picks it up; the Runner writes
WAITING, the Dispatcher resumes it later).

Structurally cannot touch an unthreaded/undefined workflow - every
WorkflowInstance this worker creates is immediately pinned to a real,
ACTIVE definition's exact version at creation time; every instance it
resumes already exists. This worker never assigns or changes a
WorkflowInstance's `workflow_definition_id`/`version` pin after
creation - doing so would violate the approved Compatibility Policy
("There must never be automatic or manual engine-driven migration of
running Workflow Instances to another definition version"), and there
is simply no code path here that could.

Same single-instance, sequential-loop simplification already established
by every other worker in this project (no SELECT...FOR UPDATE SKIP
LOCKED) - matches the actual single-replica reality of this project's
docker-compose.yml today. Adding row-level claiming here is additive if
this worker is ever scaled to multiple replicas - see docs/architecture/
m7-workflow-engine-plan.md section 11.

Same third-process-entrypoint mapper-registration requirement as every
other standalone worker in this codebase - `from app.db import base as
_base` below is required, not optional decoration.
"""
import logging
import time as time_module
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import base as _base  # noqa: F401  (imports every model so relationship() string refs resolve - see module docstring)
from app.db.session import SessionLocal
from app.models.enums import EventConsumptionOutcome, WorkflowDefinitionStatus, WorkflowInstanceStatus
from app.models.event_consumption import EventConsumption
from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_event import Event
from app.models.workflow_instance import WorkflowInstance
from app.workflow_engine.actions.base import WAIT_FOR_EVENT_ACTION_KEY

logger = logging.getLogger("sales_agent.workflow_event_dispatcher_worker")


def _matches_filter(payload: dict | None, trigger_filter: dict | None) -> bool:
    """Simple equality-based filter match - deliberately not a full
    expression language, matching this project's "deterministic MVP,
    not over-built" discipline elsewhere (e.g. rules_classifier.py's own
    keyword-based MVP from M6.4). `trigger_filter=None` always matches.
    Otherwise every key in `trigger_filter` must be present in `payload`
    with an equal value - extra keys in `payload` beyond what
    `trigger_filter` names are ignored."""
    if not trigger_filter:
        return True
    if not payload:
        return False
    return all(payload.get(key) == value for key, value in trigger_filter.items())


def _matches_subject(instance_subject_id: uuid.UUID | None, event_subject_id: uuid.UUID | None) -> bool:
    """Either side being None is treated as a wildcard match - an
    instance with no subject_id waits on ANY event of the right type;
    an event with no subject_id can resume ANY waiting instance of the
    right type. Both set: must match exactly. subject_id is an opaque
    correlation key throughout the engine (see Event's own docstring) -
    this function never interprets what it identifies."""
    if instance_subject_id is None or event_subject_id is None:
        return True
    return instance_subject_id == event_subject_id


def _start_new_instances_for_event(db: Session, event: Event) -> list[uuid.UUID]:
    """Finds every ACTIVE, platform-authored WorkflowDefinition whose
    trigger matches this event, creates a WorkflowInstance for each -
    pinned to that definition's exact id AND version, permanently, per
    the Compatibility Policy - and returns the created instance ids (for
    EventConsumption bookkeeping by the caller). Business-authored
    (company_profile_id NOT NULL) definitions are explicitly excluded -
    out of scope for M7.1 (platform-authored only)."""
    created_instance_ids: list[uuid.UUID] = []
    now = datetime.now(timezone.utc)

    candidate_definitions = db.scalars(
        select(WorkflowDefinition).where(
            WorkflowDefinition.status == WorkflowDefinitionStatus.ACTIVE,
            WorkflowDefinition.trigger_event_type == event.event_type,
            WorkflowDefinition.company_profile_id.is_(None),
        )
    ).all()

    for definition in candidate_definitions:
        if not _matches_filter(event.payload, definition.trigger_filter):
            continue

        start_step_id = definition.step_graph["start_step_id"]

        instance = WorkflowInstance(
            workflow_definition_id=definition.id,
            version=definition.version,
            company_profile_id=event.company_profile_id,
            subject_type=event.subject_type,
            subject_id=event.subject_id,
            status=WorkflowInstanceStatus.RUNNING,
            current_step_id=start_step_id,
            context={},
            started_at=now,
        )
        db.add(instance)
        db.flush()
        created_instance_ids.append(instance.id)

    return created_instance_ids


def _resume_waiting_instances_for_event(db: Session, event: Event) -> list[uuid.UUID]:
    """Finds every WAITING WorkflowInstance whose pinned definition's
    CURRENT step is a wait-for-event step (action_key ==
    WAIT_FOR_EVENT_ACTION_KEY) configured for this event's event_type,
    with a compatible subject_id (see _matches_subject above). Resumes
    each by writing the reserved `_woken_by_event` context marker -
    consumed and cleared by the built-in wait-for-event pseudo-action on
    the Step Runner's next pass (Part 1, Phase 5) - and transitioning
    status back to RUNNING. This worker never re-invokes the step's
    Action itself; confirming the wait condition and advancing to the
    next step is entirely the Step Runner's job."""
    resumed_instance_ids: list[uuid.UUID] = []

    waiting_instances = db.scalars(
        select(WorkflowInstance).where(WorkflowInstance.status == WorkflowInstanceStatus.WAITING)
    ).all()

    for instance in waiting_instances:
        if not _matches_subject(instance.subject_id, event.subject_id):
            continue

        definition = db.get(WorkflowDefinition, instance.workflow_definition_id)
        if definition is None:
            continue  # defensive - RESTRICT means this can't actually happen

        step_def = definition.step_graph.get("steps", {}).get(instance.current_step_id)
        if not isinstance(step_def, dict) or step_def.get("action_key") != WAIT_FOR_EVENT_ACTION_KEY:
            continue

        action_config = step_def.get("action_config") or {}
        if action_config.get("event_type") != event.event_type:
            continue

        instance.context = {
            **instance.context,
            "_woken_by_event": {"event_type": event.event_type, "payload": event.payload},
        }
        instance.status = WorkflowInstanceStatus.RUNNING
        db.flush()
        resumed_instance_ids.append(instance.id)

    return resumed_instance_ids


def process_one_event(db: Session, event: Event) -> dict[str, int]:
    """Runs the full matching decision for one event and records
    EventConsumption rows - one row per instance actually created/
    resumed, or exactly one NO_MATCH row (workflow_instance_id=None) if
    neither matching pass produced anything. Never raises for an
    ordinary event with no matches - only for a genuine unexpected
    error, left to the caller's try/except, same discipline as every
    other worker loop in this codebase. One commit for the whole event -
    see this module's own docstring for why the Dispatcher's write here
    can safely be one atomic unit (no external side effect, unlike a
    real Action invocation)."""
    now = datetime.now(timezone.utc)
    counts = {"started_new_instance": 0, "resumed_instance": 0, "no_match": 0}

    started_instance_ids = _start_new_instances_for_event(db, event)
    for instance_id in started_instance_ids:
        db.add(
            EventConsumption(
                event_id=event.id, workflow_instance_id=instance_id, outcome=EventConsumptionOutcome.STARTED_NEW_INSTANCE, consumed_at=now
            )
        )
        counts["started_new_instance"] += 1

    resumed_instance_ids = _resume_waiting_instances_for_event(db, event)
    for instance_id in resumed_instance_ids:
        db.add(
            EventConsumption(
                event_id=event.id, workflow_instance_id=instance_id, outcome=EventConsumptionOutcome.RESUMED_INSTANCE, consumed_at=now
            )
        )
        counts["resumed_instance"] += 1

    if not started_instance_ids and not resumed_instance_ids:
        db.add(EventConsumption(event_id=event.id, workflow_instance_id=None, outcome=EventConsumptionOutcome.NO_MATCH, consumed_at=now))
        counts["no_match"] += 1

    db.commit()
    return counts


def run_one_tick() -> dict[str, int]:
    """One pass over the current unconsumed-event backlog, up to
    WORKFLOW_EVENT_DISPATCHER_BATCH_SIZE events, ordered by
    Event.sequence_no (the true total order - see that model's own
    docstring for why a timestamp/UUID alone isn't sufficient).
    "Unconsumed" means NO EventConsumption row exists for this event at
    all (a LEFT JOIN ... WHERE NULL, not a check against the unique
    constraint) - see EventConsumption's own docstring for exactly why
    that distinction matters for idempotent tick behavior."""
    db = SessionLocal()
    try:
        candidate_ids = list(
            db.scalars(
                select(Event.id)
                .outerjoin(EventConsumption, EventConsumption.event_id == Event.id)
                .where(EventConsumption.id.is_(None))
                .order_by(Event.sequence_no.asc())
                .limit(settings.WORKFLOW_EVENT_DISPATCHER_BATCH_SIZE)
            )
        )
    finally:
        db.close()

    totals = {"started_new_instance": 0, "resumed_instance": 0, "no_match": 0}
    for event_id in candidate_ids:
        # Fresh session per event - one event's failure must never
        # poison the transaction state for the next one, same discipline
        # as every other worker loop in this codebase.
        db = SessionLocal()
        try:
            event = db.get(Event, event_id)
            if event is not None:
                counts = process_one_event(db, event)
                for key, value in counts.items():
                    totals[key] = totals.get(key, 0) + value
        except Exception:  # noqa: BLE001 - the worker loop must survive one bad event
            logger.exception("Unhandled error dispatching Event %s", event_id)
            db.rollback()
        finally:
            db.close()

    return totals


def run_forever() -> None:  # pragma: no cover - the loop itself isn't unit-testable
    logger.info(
        "Workflow Event Dispatcher starting - poll_interval=%ss batch_size=%s",
        settings.WORKFLOW_EVENT_DISPATCHER_POLL_INTERVAL_SECONDS,
        settings.WORKFLOW_EVENT_DISPATCHER_BATCH_SIZE,
    )
    while True:
        try:
            counts = run_one_tick()
            if any(counts.values()):
                logger.info("Workflow Event Dispatcher tick: %s", counts)
        except Exception:  # noqa: BLE001 - one bad tick must never kill the worker process
            logger.exception("Unhandled error in Workflow Event Dispatcher tick")
        time_module.sleep(settings.WORKFLOW_EVENT_DISPATCHER_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
