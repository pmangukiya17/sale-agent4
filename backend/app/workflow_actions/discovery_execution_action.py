"""
DiscoveryExecutionAction - M8.8 (Live AI Workflow Visualization). The
Discovery-owned bridge Action that lets a DiscoverySearch run through the
M7 Workflow Engine instead of only synchronously in-request, the same
"domain imports engine, never the reverse" shape RecordExecutionAction/
SupervisorInvocationAction already establish one file over in this same
package.

Per this module's own contract (app.workflow_engine.actions.base.Action):
no DB session is passed into execute() - this Action opens its own,
exactly like every domain Action in this package that needs the database
must (see that module's own docstring, "An Action that needs the DB opens
its own session internally").

How the Action finds out WHICH search to run: the Event Dispatcher worker
creates every new WorkflowInstance with `context={}` (empty) - it does NOT
seed context from the triggering Event's payload (see
event_dispatcher_worker.py's own instance-creation code). So this Action
cannot read discovery_search_id out of input_data.context; instead it
looks at the INSTANCE itself: instance.subject_type/subject_id, set by the
Event Dispatcher directly from the triggering Event's own subject_type/
subject_id columns (app/api/routes/discovery_searches.py publishes
DISCOVERY_SEARCH_RUN_REQUESTED_EVENT_TYPE with
subject_type="discovery_search", subject_id=search.id - see that route's
own docstring).

The one other piece of context genuinely missing from the instance itself
is WHICH USER triggered this run (app.discovery.pipeline.run_discovery_search
requires a real User for DiscoveryRun.triggered_by_user_id - a real,
NOT NULL audit field, not something this Action may invent a placeholder
for). This Action recovers it honestly rather than guessing: it walks
EventConsumption (workflow_instance_id -> event_id) back to the actual
triggering Event, and reads actor_type/actor_id off THAT row -
Event.actor_type/actor_id (M8.5 Event Backbone columns) exist for exactly
this ("who or what produced this event" - see app.models.workflow_event.
Event's own docstring) and are already populated by the route with
actor_type="user", actor_id=str(current_user.id). If any link in that
chain is missing (no EventConsumption found, no actor recorded, or the
actor_id doesn't parse as a real User), this Action fails loudly
(ActionOutcome.FAILURE with a specific error) rather than silently
running the search as an unknown/system user - a real audit trail matters
here exactly as much as it does on the synchronous path.
"""
import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.discovery.pipeline import DiscoveryConfigError, run_discovery_search
from app.models.discovery_search import DiscoverySearch
from app.models.event_consumption import EventConsumption
from app.models.user import User
from app.models.workflow_event import Event
from app.models.workflow_instance import WorkflowInstance
from app.workflow_engine.actions.base import Action, ActionInput, ActionOutcome, ActionOutput
from app.workflow_engine.actions.registry import is_action_registered, register_action

DISCOVERY_EXECUTION_ACTION_KEY = "discovery.execute_search"


def _resolve_triggering_user(db, workflow_instance_id: uuid.UUID) -> User | None:
    """Walks WorkflowInstance -> (the EventConsumption row that started it)
    -> Event.actor_id -> User. Returns None (never raises) if any link is
    missing or malformed - the caller decides how to report that as a
    FAILURE, this helper just tells the truth about what it found."""
    consumption = db.scalars(
        select(EventConsumption)
        .where(
            EventConsumption.workflow_instance_id == workflow_instance_id,
        )
        .order_by(EventConsumption.consumed_at.asc())
        .limit(1)
    ).first()
    if consumption is None:
        return None

    event = db.get(Event, consumption.event_id)
    if event is None or event.actor_type != "user" or not event.actor_id:
        return None

    try:
        user_id = uuid.UUID(event.actor_id)
    except ValueError:
        return None

    return db.get(User, user_id)


class DiscoveryExecutionAction(Action):
    def execute(self, input_data: ActionInput) -> ActionOutput:
        db = SessionLocal()
        try:
            instance = db.get(WorkflowInstance, input_data.workflow_instance_id)
            if instance is None:
                return ActionOutput(status=ActionOutcome.FAILURE, error="WorkflowInstance not found")

            if instance.subject_type != "discovery_search" or instance.subject_id is None:
                return ActionOutput(
                    status=ActionOutcome.FAILURE,
                    error=f"DiscoveryExecutionAction requires subject_type='discovery_search' with a subject_id; got "
                    f"subject_type={instance.subject_type!r} subject_id={instance.subject_id!r}",
                )

            search = db.get(DiscoverySearch, instance.subject_id)
            if search is None:
                return ActionOutput(
                    status=ActionOutcome.FAILURE,
                    error=f"DiscoverySearch {instance.subject_id} no longer exists",
                )

            triggered_by_user = _resolve_triggering_user(db, instance.id)
            if triggered_by_user is None:
                return ActionOutput(
                    status=ActionOutcome.FAILURE,
                    error="Could not resolve the user who triggered this search run (missing/malformed "
                    "EventConsumption or Event.actor_id) - refusing to run without a real audit trail",
                )

            if not search.provider_keys:
                return ActionOutput(status=ActionOutcome.FAILURE, error="This search has no providers enabled")

            try:
                job = run_discovery_search(db, search, triggered_by_user)
            except DiscoveryConfigError as exc:
                return ActionOutput(status=ActionOutcome.FAILURE, error=str(exc))

            return ActionOutput(status=ActionOutcome.SUCCESS, result={"discovery_job_id": str(job.id)})
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


# Idempotent, same defensive idiom as every other Action registration in
# this package (RecordExecutionAction/SupervisorInvocationAction).
if not is_action_registered(DISCOVERY_EXECUTION_ACTION_KEY):
    register_action(DISCOVERY_EXECUTION_ACTION_KEY, DiscoveryExecutionAction())
