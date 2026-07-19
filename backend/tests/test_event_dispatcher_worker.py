"""
Real, DB-backed tests of app/workflow_engine/event_dispatcher_worker.py
- M7.1 Part 1, Phase 4. Covers: new-instance creation pinned to the
correct version, resume-from-WAITING via the reserved `_woken_by_event`
context marker, EventConsumption idempotency (a rerun is a true no-op),
DRAFT/DEPRECATED definitions are never matched, trigger_filter/subject_id
matching, and that one event can legitimately produce more than one
EventConsumption row.

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_event_dispatcher_worker
"""
import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.models.company_profile import CompanyProfile
from app.models.enums import EventConsumptionOutcome, UserRole, WorkflowInstanceStatus
from app.models.event_consumption import EventConsumption
from app.models.user import User
from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_event import Event
from app.models.workflow_instance import WorkflowInstance
from app.workflow_engine import event_dispatcher_worker
from app.workflow_engine.actions.base import WAIT_FOR_EVENT_ACTION_KEY, Action, ActionInput, ActionOutcome, ActionOutput
from app.workflow_engine.actions.registry import ACTION_REGISTRY, register_action
from app.workflow_engine.definitions import activate_definition, create_draft_definition, deprecate_definition
from app.workflow_engine.events import publish_event


def _now():
    return datetime.now(timezone.utc)


class _FakeAction(Action):
    def execute(self, input_data: ActionInput) -> ActionOutput:
        return ActionOutput(status=ActionOutcome.SUCCESS)


def _single_step_graph() -> dict:
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


def _wait_step_graph(event_type: str) -> dict:
    return {
        "start_step_id": "step_1",
        "steps": {
            "step_1": {
                "action_key": WAIT_FOR_EVENT_ACTION_KEY,
                "action_config": {"event_type": event_type},
                "transitions": {"success": None, "failure": None},
                "max_attempts": 1,
            }
        },
    }


class TestEventDispatcherWorker(unittest.TestCase):
    def setUp(self):
        self._saved_registry = dict(ACTION_REGISTRY)
        ACTION_REGISTRY.clear()
        register_action("test.registered_action", _FakeAction())

        self.db = SessionLocal()

        self.user = User(email=f"m7.1-dispatcher-test-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M7.1 Dispatcher Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.commit()

        self._test_key_prefix = f"test-dispatcher-{uuid.uuid4()}"

    def tearDown(self):
        self.db.rollback()
        ACTION_REGISTRY.clear()
        ACTION_REGISTRY.update(self._saved_registry)

        # EventConsumption rows must be deleted BEFORE Event/WorkflowInstance
        # - event_consumptions.event_id is ondelete="RESTRICT" (deliberately),
        # and this test class deliberately produces plenty of NO_MATCH rows
        # (workflow_instance_id=NULL, e.g. test_no_active_definition_produces_
        # no_match_consumption) that are NOT reachable via WorkflowInstance's
        # own CASCADE below - only a STARTED_NEW_INSTANCE/RESUMED_INSTANCE row
        # is. Deleting EventConsumption explicitly, first, by BOTH event_id
        # and workflow_instance_id membership, handles every row this test
        # class can produce uniformly.
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
        self.db.query(WorkflowDefinition).filter(WorkflowDefinition.key.like(f"{self._test_key_prefix}%")).delete(
            synchronize_session=False
        )
        self.db.commit()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    def _activated_definition(self, key_suffix: str, *, trigger_event_type: str, step_graph: dict, trigger_filter: dict | None = None) -> WorkflowDefinition:
        draft = create_draft_definition(
            self.db,
            key=f"{self._test_key_prefix}-{key_suffix}",
            trigger_event_type=trigger_event_type,
            step_graph=step_graph,
            trigger_filter=trigger_filter,
        )
        return activate_definition(self.db, draft)

    # --- new-instance creation ------------------------------------------
    def test_matching_event_creates_new_instance_pinned_to_active_version(self):
        definition = self._activated_definition("basic", trigger_event_type="test.trigger.basic", step_graph=_single_step_graph())
        event = publish_event(self.db, event_type="test.trigger.basic", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()

        counts = event_dispatcher_worker.run_one_tick()
        self.assertEqual(counts["started_new_instance"], 1)

        instances = self.db.query(WorkflowInstance).filter(WorkflowInstance.company_profile_id == self.company_profile.id).all()
        self.assertEqual(len(instances), 1)
        instance = instances[0]
        self.assertEqual(instance.workflow_definition_id, definition.id)
        self.assertEqual(instance.version, definition.version)
        self.assertEqual(instance.current_step_id, "step_1")
        self.assertEqual(instance.status, WorkflowInstanceStatus.RUNNING)

        consumption = self.db.query(EventConsumption).filter(EventConsumption.event_id == event.id).one()
        self.assertEqual(consumption.outcome, EventConsumptionOutcome.STARTED_NEW_INSTANCE)
        self.assertEqual(consumption.workflow_instance_id, instance.id)

    def test_no_active_definition_produces_no_match_consumption(self):
        event = publish_event(
            self.db, event_type="test.trigger.nothing.listens", company_profile_id=self.company_profile.id, source="tests"
        )
        self.db.commit()

        event_dispatcher_worker.run_one_tick()

        consumption = self.db.query(EventConsumption).filter(EventConsumption.event_id == event.id).one()
        self.assertEqual(consumption.outcome, EventConsumptionOutcome.NO_MATCH)
        self.assertIsNone(consumption.workflow_instance_id)

    def test_draft_definition_is_never_matched(self):
        create_draft_definition(
            self.db, key=f"{self._test_key_prefix}-draft-only", trigger_event_type="test.trigger.draft", step_graph=_single_step_graph()
        )
        event = publish_event(self.db, event_type="test.trigger.draft", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()

        event_dispatcher_worker.run_one_tick()

        consumption = self.db.query(EventConsumption).filter(EventConsumption.event_id == event.id).one()
        self.assertEqual(consumption.outcome, EventConsumptionOutcome.NO_MATCH)

    def test_deprecated_definition_is_never_matched(self):
        definition = self._activated_definition("deprecated", trigger_event_type="test.trigger.deprecated", step_graph=_single_step_graph())
        deprecate_definition(self.db, definition)
        event = publish_event(self.db, event_type="test.trigger.deprecated", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()

        event_dispatcher_worker.run_one_tick()

        consumption = self.db.query(EventConsumption).filter(EventConsumption.event_id == event.id).one()
        self.assertEqual(consumption.outcome, EventConsumptionOutcome.NO_MATCH)

    def test_trigger_filter_must_match_payload(self):
        self._activated_definition(
            "filtered", trigger_event_type="test.trigger.filtered", step_graph=_single_step_graph(), trigger_filter={"region": "eu"}
        )
        non_matching_event = publish_event(
            self.db, event_type="test.trigger.filtered", company_profile_id=self.company_profile.id, source="tests", payload={"region": "us"}
        )
        self.db.commit()
        event_dispatcher_worker.run_one_tick()
        self.assertEqual(
            self.db.query(EventConsumption).filter(EventConsumption.event_id == non_matching_event.id).one().outcome,
            EventConsumptionOutcome.NO_MATCH,
        )

        matching_event = publish_event(
            self.db, event_type="test.trigger.filtered", company_profile_id=self.company_profile.id, source="tests", payload={"region": "eu"}
        )
        self.db.commit()
        event_dispatcher_worker.run_one_tick()
        self.assertEqual(
            self.db.query(EventConsumption).filter(EventConsumption.event_id == matching_event.id).one().outcome,
            EventConsumptionOutcome.STARTED_NEW_INSTANCE,
        )

    def test_one_event_can_start_instances_for_multiple_definitions(self):
        self._activated_definition("multi-a", trigger_event_type="test.trigger.shared", step_graph=_single_step_graph())
        self._activated_definition("multi-b", trigger_event_type="test.trigger.shared", step_graph=_single_step_graph())
        event = publish_event(self.db, event_type="test.trigger.shared", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()

        counts = event_dispatcher_worker.run_one_tick()
        self.assertEqual(counts["started_new_instance"], 2)

        consumptions = self.db.query(EventConsumption).filter(EventConsumption.event_id == event.id).all()
        self.assertEqual(len(consumptions), 2)

    # --- idempotency -----------------------------------------------------
    def test_rerun_is_idempotent_no_duplicate_instances(self):
        self._activated_definition("idempotent", trigger_event_type="test.trigger.idempotent", step_graph=_single_step_graph())
        publish_event(self.db, event_type="test.trigger.idempotent", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()

        first_counts = event_dispatcher_worker.run_one_tick()
        second_counts = event_dispatcher_worker.run_one_tick()

        self.assertEqual(first_counts["started_new_instance"], 1)
        self.assertEqual(second_counts["started_new_instance"], 0, "a rerun with no new events must be a true no-op")

        instances = self.db.query(WorkflowInstance).filter(WorkflowInstance.company_profile_id == self.company_profile.id).all()
        self.assertEqual(len(instances), 1, "rerunning the dispatcher must never create a duplicate instance")

    # --- resume-from-waiting -----------------------------------------------
    def test_resumes_waiting_instance_on_matching_event(self):
        definition = self._activated_definition("wait", trigger_event_type="test.never.fires", step_graph=_wait_step_graph("test.resume.me"))
        subject_id = uuid.uuid4()
        instance = WorkflowInstance(
            workflow_definition_id=definition.id,
            version=definition.version,
            company_profile_id=self.company_profile.id,
            subject_id=subject_id,
            status=WorkflowInstanceStatus.WAITING,
            current_step_id="step_1",
            context={},
        )
        self.db.add(instance)
        self.db.commit()

        event = publish_event(
            self.db, event_type="test.resume.me", company_profile_id=self.company_profile.id, source="tests",
            subject_id=subject_id, payload={"some": "data"},
        )
        self.db.commit()

        counts = event_dispatcher_worker.run_one_tick()
        self.assertEqual(counts["resumed_instance"], 1)

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.RUNNING)
        self.assertEqual(instance.context.get("_woken_by_event", {}).get("event_type"), "test.resume.me")
        self.assertEqual(instance.context.get("_woken_by_event", {}).get("payload"), {"some": "data"})

    def test_resume_respects_subject_id_matching(self):
        definition = self._activated_definition(
            "wait-subject", trigger_event_type="test.never.fires", step_graph=_wait_step_graph("test.resume.subject")
        )
        instance = WorkflowInstance(
            workflow_definition_id=definition.id,
            version=definition.version,
            company_profile_id=self.company_profile.id,
            subject_id=uuid.uuid4(),
            status=WorkflowInstanceStatus.WAITING,
            current_step_id="step_1",
            context={},
        )
        self.db.add(instance)
        self.db.commit()

        wrong_subject_event = publish_event(
            self.db, event_type="test.resume.subject", company_profile_id=self.company_profile.id, source="tests", subject_id=uuid.uuid4()
        )
        self.db.commit()

        event_dispatcher_worker.run_one_tick()

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.WAITING, "an event for a DIFFERENT subject must never resume this instance")
        self.assertEqual(
            self.db.query(EventConsumption).filter(EventConsumption.event_id == wrong_subject_event.id).one().outcome,
            EventConsumptionOutcome.NO_MATCH,
        )

    def test_resume_ignores_wrong_event_type(self):
        definition = self._activated_definition(
            "wait-type", trigger_event_type="test.never.fires", step_graph=_wait_step_graph("test.the.right.event")
        )
        instance = WorkflowInstance(
            workflow_definition_id=definition.id,
            version=definition.version,
            company_profile_id=self.company_profile.id,
            status=WorkflowInstanceStatus.WAITING,
            current_step_id="step_1",
            context={},
        )
        self.db.add(instance)
        self.db.commit()

        publish_event(self.db, event_type="test.the.wrong.event", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()

        event_dispatcher_worker.run_one_tick()

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.WAITING)


if __name__ == "__main__":
    unittest.main()
