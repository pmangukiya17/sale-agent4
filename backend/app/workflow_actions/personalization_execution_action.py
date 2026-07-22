"""
PersonalizationExecutionAction - M8.11 (Live AI Workflow Visualization,
Personalization). Structural mirror of DiscoveryExecutionAction (M8.8) -
see that module's own docstring for the shared reasoning (no DB session
passed in, subject_type/subject_id identify which PersonalizationRequest
to run since context starts empty, triggering user recovered via
EventConsumption -> Event.actor_id).

Simpler than Research's equivalent Action: PersonalizationRequest needs no
per-run input at all (unlike ResearchRequest's run_input - see
run_personalization_request_endpoint's own docstring, "there is no
external input to merge in"), so this Action only ever needs the
triggering Event for its actor_id, never its payload.
"""
import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.event_consumption import EventConsumption
from app.models.personalization_request import PersonalizationRequest
from app.models.user import User
from app.models.workflow_event import Event
from app.models.workflow_instance import WorkflowInstance
from app.personalization.pipeline import PersonalizationConfigError, run_personalization_request
from app.workflow_engine.actions.base import Action, ActionInput, ActionOutcome, ActionOutput
from app.workflow_engine.actions.registry import is_action_registered, register_action

PERSONALIZATION_EXECUTION_ACTION_KEY = "personalization.execute_request"


def _resolve_triggering_user(db, workflow_instance_id: uuid.UUID) -> User | None:
    consumption = db.scalars(
        select(EventConsumption)
        .where(EventConsumption.workflow_instance_id == workflow_instance_id)
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


class PersonalizationExecutionAction(Action):
    def execute(self, input_data: ActionInput) -> ActionOutput:
        db = SessionLocal()
        try:
            instance = db.get(WorkflowInstance, input_data.workflow_instance_id)
            if instance is None:
                return ActionOutput(status=ActionOutcome.FAILURE, error="WorkflowInstance not found")

            if instance.subject_type != "personalization_request" or instance.subject_id is None:
                return ActionOutput(
                    status=ActionOutcome.FAILURE,
                    error=f"PersonalizationExecutionAction requires subject_type='personalization_request' with a "
                    f"subject_id; got subject_type={instance.subject_type!r} subject_id={instance.subject_id!r}",
                )

            request = db.get(PersonalizationRequest, instance.subject_id)
            if request is None:
                return ActionOutput(
                    status=ActionOutcome.FAILURE,
                    error=f"PersonalizationRequest {instance.subject_id} no longer exists",
                )

            triggered_by_user = _resolve_triggering_user(db, instance.id)
            if triggered_by_user is None:
                return ActionOutput(
                    status=ActionOutcome.FAILURE,
                    error="Could not resolve the user who triggered this personalization run (missing/malformed "
                    "EventConsumption or Event.actor_id) - refusing to run without a real audit trail",
                )

            try:
                job = run_personalization_request(db, request, triggered_by_user)
            except PersonalizationConfigError as exc:
                return ActionOutput(status=ActionOutcome.FAILURE, error=str(exc))

            return ActionOutput(status=ActionOutcome.SUCCESS, result={"personalization_job_id": str(job.id)})
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


if not is_action_registered(PERSONALIZATION_EXECUTION_ACTION_KEY):
    register_action(PERSONALIZATION_EXECUTION_ACTION_KEY, PersonalizationExecutionAction())
