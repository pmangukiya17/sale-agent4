"""
ResearchExecutionAction - M8.13 (Live AI Workflow Visualization, Research).
Exact structural mirror of DiscoveryExecutionAction (M8.8) - see that
module's own docstring for the full reasoning this one repeats: no DB
session is passed into execute() (opens its own), the WorkflowInstance's
subject_type/subject_id (not context, which starts empty) identifies
which ResearchRequest to run, and the triggering user is recovered via
EventConsumption -> Event.actor_id rather than invented.

One real difference from Discovery, disclosed rather than glossed over:
ResearchRequest is NOT a reusable saved config (see research_request.py's
own docstring) - run_research_request() needs a per-run `run_input` dict
(e.g. the manual_document provider's documents) that has nowhere else to
live. Since WorkflowInstance.context starts empty exactly like Discovery's
does, this Action recovers `run_input` the same way it recovers the
triggering user: by reading it off the SAME triggering Event's `payload`
(app/api/routes/research_requests.py publishes it there - see that
route's own docstring). Event.payload is already-existing, already-opaque
JSONB Discovery's own trigger event simply had no use for; Research is
the first workflow that puts something more than routing metadata there.
"""
import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.event_consumption import EventConsumption
from app.models.research_request import ResearchRequest
from app.models.user import User
from app.models.workflow_event import Event
from app.models.workflow_instance import WorkflowInstance
from app.research.pipeline import ResearchConfigError, run_research_request
from app.workflow_engine.actions.base import Action, ActionInput, ActionOutcome, ActionOutput
from app.workflow_engine.actions.registry import is_action_registered, register_action

RESEARCH_EXECUTION_ACTION_KEY = "research.execute_request"


def _resolve_triggering_event(db, workflow_instance_id: uuid.UUID) -> Event | None:
    """Same walk as DiscoveryExecutionAction's _resolve_triggering_user,
    but returns the Event itself so this module can read BOTH actor_id
    (who) and payload (run_input) off the one row, instead of two
    separate lookups for the same fact."""
    consumption = db.scalars(
        select(EventConsumption)
        .where(EventConsumption.workflow_instance_id == workflow_instance_id)
        .order_by(EventConsumption.consumed_at.asc())
        .limit(1)
    ).first()
    if consumption is None:
        return None
    return db.get(Event, consumption.event_id)


def _resolve_triggering_user(db, event: Event | None) -> User | None:
    if event is None or event.actor_type != "user" or not event.actor_id:
        return None
    try:
        user_id = uuid.UUID(event.actor_id)
    except ValueError:
        return None
    return db.get(User, user_id)


class ResearchExecutionAction(Action):
    def execute(self, input_data: ActionInput) -> ActionOutput:
        db = SessionLocal()
        try:
            instance = db.get(WorkflowInstance, input_data.workflow_instance_id)
            if instance is None:
                return ActionOutput(status=ActionOutcome.FAILURE, error="WorkflowInstance not found")

            if instance.subject_type != "research_request" or instance.subject_id is None:
                return ActionOutput(
                    status=ActionOutcome.FAILURE,
                    error=f"ResearchExecutionAction requires subject_type='research_request' with a subject_id; got "
                    f"subject_type={instance.subject_type!r} subject_id={instance.subject_id!r}",
                )

            request = db.get(ResearchRequest, instance.subject_id)
            if request is None:
                return ActionOutput(
                    status=ActionOutcome.FAILURE,
                    error=f"ResearchRequest {instance.subject_id} no longer exists",
                )

            event = _resolve_triggering_event(db, instance.id)
            triggered_by_user = _resolve_triggering_user(db, event)
            if triggered_by_user is None:
                return ActionOutput(
                    status=ActionOutcome.FAILURE,
                    error="Could not resolve the user who triggered this research run (missing/malformed "
                    "EventConsumption or Event.actor_id) - refusing to run without a real audit trail",
                )

            run_input = (event.payload or {}).get("run_input") if event else None

            try:
                job = run_research_request(db, request, triggered_by_user, run_input=run_input)
            except ResearchConfigError as exc:
                return ActionOutput(status=ActionOutcome.FAILURE, error=str(exc))

            return ActionOutput(status=ActionOutcome.SUCCESS, result={"research_job_id": str(job.id)})
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


# Idempotent, same defensive idiom as every other Action registration in
# this package.
if not is_action_registered(RESEARCH_EXECUTION_ACTION_KEY):
    register_action(RESEARCH_EXECUTION_ACTION_KEY, ResearchExecutionAction())
