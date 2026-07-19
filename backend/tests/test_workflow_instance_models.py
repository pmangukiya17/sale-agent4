"""
Real, DB-backed tests of the WorkflowInstance/WorkflowStepInvocation/
EventConsumption models and their constraints - M7.1 Part 1, Phase 3.
No worker logic yet (that's Phase 4/5) - rows are constructed directly,
same "test the data model in isolation first" precedent as
test_conversation_models.py (M6.1).

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_workflow_instance_models
"""
import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.models.company_profile import CompanyProfile
from app.models.enums import (
    EventConsumptionOutcome,
    UserRole,
    WorkflowInstanceStatus,
    WorkflowStepInvocationStatus,
)
from app.models.event_consumption import EventConsumption
from app.models.user import User
from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_event import Event
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step_invocation import WorkflowStepInvocation
from app.workflow_engine.actions.base import Action, ActionInput, ActionOutcome, ActionOutput
from app.workflow_engine.actions.registry import ACTION_REGISTRY, register_action
from app.workflow_engine.definitions import activate_definition, create_draft_definition
from app.workflow_engine.events import publish_event


def _now():
    return datetime.now(timezone.utc)


class _FakeAction(Action):
    def execute(self, input_data: ActionInput) -> ActionOutput:
        return ActionOutput(status=ActionOutcome.SUCCESS)


def _valid_graph() -> dict:
    return {
        "start_step_id": "step_1",
        "steps": {
            "step_1": {
                "action_key": "test.registered_action",
                "transitions": {"success": None, "failure": None},
                "max_attempts": 1,
            }
        },
    }


class TestWorkflowInstanceModels(unittest.TestCase):
    def setUp(self):
        self._saved_registry = dict(ACTION_REGISTRY)
        ACTION_REGISTRY.clear()
        register_action("test.registered_action", _FakeAction())

        self.db = SessionLocal()

        self.user = User(email=f"m7.1-instance-models-test-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M7.1 Instance Models Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.commit()

        test_key = f"test-workflow-{uuid.uuid4()}"
        draft = create_draft_definition(self.db, key=test_key, trigger_event_type="test.trigger", step_graph=_valid_graph())
        self.definition = activate_definition(self.db, draft)

    def tearDown(self):
        self.db.rollback()
        ACTION_REGISTRY.clear()
        ACTION_REGISTRY.update(self._saved_registry)

        # EventConsumption rows must be deleted BEFORE Event/WorkflowInstance
        # - event_consumptions.event_id is ondelete="RESTRICT" (deliberately
        # - see that model's own docstring), and a NO_MATCH row's
        # workflow_instance_id is NULL by design (see
        # test_event_consumption_no_match_allows_null_instance below), so it
        # is NOT reachable via WorkflowInstance's own CASCADE the way a
        # STARTED_NEW_INSTANCE/RESUMED_INSTANCE row is. Deleting
        # EventConsumption explicitly, first, by BOTH event_id and
        # workflow_instance_id membership, handles every row this test class
        # can create uniformly rather than relying on cascade-through-instance
        # for only the ones that happen to have one.
        event_ids = select(Event.id).where(Event.company_profile_id == self.company_profile.id)
        instance_ids = select(WorkflowInstance.id).where(WorkflowInstance.company_profile_id == self.company_profile.id)
        self.db.query(EventConsumption).filter(
            or_(EventConsumption.event_id.in_(event_ids), EventConsumption.workflow_instance_id.in_(instance_ids))
        ).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(WorkflowInstance).filter(WorkflowInstance.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()
        self.db.query(Event).filter(Event.company_profile_id == self.company_profile.id).delete(synchronize_session=False)
        self.db.commit()
        self.db.query(WorkflowDefinition).filter(WorkflowDefinition.id == self.definition.id).delete()
        self.db.commit()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    # --- fixture helper -------------------------------------------------
    def _make_instance(self, **overrides) -> WorkflowInstance:
        kwargs = dict(
            workflow_definition_id=self.definition.id,
            version=self.definition.version,
            company_profile_id=self.company_profile.id,
            status=WorkflowInstanceStatus.RUNNING,
            current_step_id="step_1",
        )
        kwargs.update(overrides)
        instance = WorkflowInstance(**kwargs)
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    # --- WorkflowInstance ----------------------------------------------------
    def test_create_workflow_instance_round_trip(self):
        subject_id = uuid.uuid4()
        instance = self._make_instance(subject_type="test_subject", subject_id=subject_id)

        self.assertEqual(instance.workflow_definition_id, self.definition.id)
        self.assertEqual(instance.version, self.definition.version)
        self.assertEqual(instance.status, WorkflowInstanceStatus.RUNNING)
        self.assertEqual(instance.current_step_id, "step_1")
        self.assertEqual(instance.context, {})
        self.assertEqual(instance.subject_id, subject_id)
        self.assertIsNone(instance.claimed_by)
        self.assertIsNone(instance.claimed_at)

    def test_workflow_instance_default_status_is_pending(self):
        instance = WorkflowInstance(
            workflow_definition_id=self.definition.id,
            version=self.definition.version,
            company_profile_id=self.company_profile.id,
            current_step_id="step_1",
        )
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)

        self.assertEqual(instance.status, WorkflowInstanceStatus.PENDING)

    def test_deleting_definition_with_instances_is_restricted(self):
        self._make_instance()
        with self.assertRaises(IntegrityError):
            self.db.delete(self.definition)
            self.db.commit()
        self.db.rollback()

    # --- WorkflowStepInvocation ------------------------------------------
    def test_create_workflow_step_invocation_round_trip(self):
        instance = self._make_instance()
        invocation = WorkflowStepInvocation(
            workflow_instance_id=instance.id,
            step_id="step_1",
            action_key="test.registered_action",
            attempt_number=1,
            status=WorkflowStepInvocationStatus.SUCCEEDED,
            input_snapshot={"foo": "bar"},
            output={"result": "ok"},
            started_at=_now(),
            completed_at=_now(),
        )
        self.db.add(invocation)
        self.db.commit()
        self.db.refresh(invocation)

        self.assertEqual(invocation.workflow_instance_id, instance.id)
        self.assertEqual(invocation.status, WorkflowStepInvocationStatus.SUCCEEDED)
        self.assertEqual(invocation.input_snapshot, {"foo": "bar"})
        self.assertEqual(invocation.output, {"result": "ok"})
        self.assertIsNone(invocation.error)

    def test_step_invocations_cascade_delete_with_instance(self):
        instance = self._make_instance()
        invocation = WorkflowStepInvocation(
            workflow_instance_id=instance.id,
            step_id="step_1",
            action_key="test.registered_action",
            status=WorkflowStepInvocationStatus.SUCCEEDED,
        )
        self.db.add(invocation)
        self.db.commit()
        invocation_id = invocation.id

        self.db.delete(instance)
        self.db.commit()

        self.assertIsNone(self.db.get(WorkflowStepInvocation, invocation_id))

    def test_multiple_attempts_are_separate_rows(self):
        instance = self._make_instance()
        first_attempt = WorkflowStepInvocation(
            workflow_instance_id=instance.id, step_id="step_1", action_key="test.registered_action",
            attempt_number=1, status=WorkflowStepInvocationStatus.FAILED, error="transient error",
        )
        second_attempt = WorkflowStepInvocation(
            workflow_instance_id=instance.id, step_id="step_1", action_key="test.registered_action",
            attempt_number=2, status=WorkflowStepInvocationStatus.SUCCEEDED,
        )
        self.db.add_all([first_attempt, second_attempt])
        self.db.commit()

        rows = (
            self.db.query(WorkflowStepInvocation)
            .filter(WorkflowStepInvocation.workflow_instance_id == instance.id)
            .order_by(WorkflowStepInvocation.attempt_number)
            .all()
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].status, WorkflowStepInvocationStatus.FAILED)
        self.assertEqual(rows[1].status, WorkflowStepInvocationStatus.SUCCEEDED)

    # --- EventConsumption ---------------------------------------------------
    def test_event_consumption_round_trip_started_new_instance(self):
        event = publish_event(self.db, event_type="test.trigger", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()
        instance = self._make_instance()

        consumption = EventConsumption(
            event_id=event.id, workflow_instance_id=instance.id, outcome=EventConsumptionOutcome.STARTED_NEW_INSTANCE, consumed_at=_now()
        )
        self.db.add(consumption)
        self.db.commit()
        self.db.refresh(consumption)

        self.assertEqual(consumption.event_id, event.id)
        self.assertEqual(consumption.workflow_instance_id, instance.id)
        self.assertEqual(consumption.outcome, EventConsumptionOutcome.STARTED_NEW_INSTANCE)

    def test_event_consumption_no_match_allows_null_instance(self):
        event = publish_event(self.db, event_type="test.unrelated", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()

        consumption = EventConsumption(event_id=event.id, workflow_instance_id=None, outcome=EventConsumptionOutcome.NO_MATCH, consumed_at=_now())
        self.db.add(consumption)
        self.db.commit()
        self.db.refresh(consumption)

        self.assertIsNone(consumption.workflow_instance_id)
        self.assertEqual(consumption.outcome, EventConsumptionOutcome.NO_MATCH)

    def test_event_consumption_rejects_duplicate_event_instance_pair(self):
        event = publish_event(self.db, event_type="test.trigger", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()
        instance = self._make_instance()

        first = EventConsumption(event_id=event.id, workflow_instance_id=instance.id, outcome=EventConsumptionOutcome.RESUMED_INSTANCE, consumed_at=_now())
        self.db.add(first)
        self.db.commit()

        duplicate = EventConsumption(event_id=event.id, workflow_instance_id=instance.id, outcome=EventConsumptionOutcome.RESUMED_INSTANCE, consumed_at=_now())
        self.db.add(duplicate)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_event_consumption_cascade_deletes_with_instance(self):
        event = publish_event(self.db, event_type="test.trigger", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()
        instance = self._make_instance()
        consumption = EventConsumption(event_id=event.id, workflow_instance_id=instance.id, outcome=EventConsumptionOutcome.STARTED_NEW_INSTANCE, consumed_at=_now())
        self.db.add(consumption)
        self.db.commit()
        consumption_id = consumption.id

        self.db.delete(instance)
        self.db.commit()

        self.assertIsNone(self.db.get(EventConsumption, consumption_id))

    def test_deleting_a_consumed_event_is_restricted(self):
        event = publish_event(self.db, event_type="test.trigger", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()
        instance = self._make_instance()
        consumption = EventConsumption(event_id=event.id, workflow_instance_id=instance.id, outcome=EventConsumptionOutcome.STARTED_NEW_INSTANCE, consumed_at=_now())
        self.db.add(consumption)
        self.db.commit()

        with self.assertRaises(IntegrityError):
            self.db.delete(event)
            self.db.commit()
        self.db.rollback()


if __name__ == "__main__":
    unittest.main()
