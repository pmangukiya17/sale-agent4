"""
End-to-end verification of M7.1 Part 2's pilot workflow - THE reference
verification for all future workflows (per the approved design). Unlike
Part 1's own unit tests (which use synthetic WorkflowDefinitions and fake
Actions to test each layer of the engine in isolation), this file drives
the REAL production path start to finish:

    real Conversation creation (thread_builder.process_one_message)
        -> real publish_event("conversation.created")
        -> Event stored (transactional outbox)
        -> real Event Dispatcher tick
        -> real WorkflowInstance created, pinned to the REAL activated
           "conversation_created_pilot" WorkflowDefinition (authored via
           app.workflow_bootstrap.activate_builtin_workflows - the same
           bootstrap app.main's own lifespan() calls on every real boot)
        -> real Step Runner tick
        -> real, registered app.workflow_actions.RecordExecutionAction
           actually invoked
        -> WorkflowInstance COMPLETED

Also proves the negative case that makes the whole design meaningful:
matching an EXISTING conversation must never publish conversation.created
- only a genuinely NEW Conversation does.

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_pilot_workflow_e2e
"""
import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.models.company_profile import CompanyProfile
from app.models.enums import ProviderConnectionStatus, UserRole, WorkflowInstanceStatus, WorkflowStepInvocationStatus
from app.models.event_consumption import EventConsumption
from app.models.provider_connection import ProviderConnection
from app.models.user import User
from app.models.workflow_event import Event
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step_invocation import WorkflowStepInvocation

# Real production imports - deliberately not synthetic/faked, unlike
# Part 1's own unit tests. Importing app.workflow_actions registers the
# real pilot Action; activate_builtin_workflows() is the real bootstrap
# app.main's own lifespan() calls on every boot.
import app.workflow_actions  # noqa: F401  (registers RECORD_EXECUTION_ACTION_KEY for real)
from app.reply_intelligence import thread_builder
from app.reply_intelligence.thread_builder import CONVERSATION_CREATED_EVENT_TYPE
from app.workflow_actions.record_execution_action import RECORD_EXECUTION_ACTION_KEY
from app.workflow_bootstrap import activate_builtin_workflows
from app.workflow_engine import event_dispatcher_worker, step_runner_worker
from app.models.email_message import EmailMessage
from app.models.enums import MessageDirection


def _now():
    return datetime.now(timezone.utc)


class TestPilotWorkflowEndToEnd(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        # Real bootstrap - idempotent, exactly what app.main's lifespan()
        # does on every real boot. If a prior test run (or the real
        # running application) already activated this key, this is a
        # true no-op; if this is a fresh database, it authors + activates
        # v1 here, through the real governed lifecycle.
        activate_builtin_workflows(self.db)

        self.user = User(email=f"m7.1-pilot-e2e-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M7.1 Pilot E2E Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.flush()

        self.connection = ProviderConnection(
            company_profile_id=self.company_profile.id, provider_key="outlook", status=ProviderConnectionStatus.CONNECTED
        )
        self.db.add(self.connection)
        self.db.commit()

    def tearDown(self):
        self.db.rollback()  # discard any uncommitted state from a failed assertion mid-test

        # Same FK-RESTRICT-safe ordering established in Part 1's own
        # teardown fixes (test_workflow_instance_models.py et al.):
        # EventConsumption before Event/WorkflowInstance,
        # WorkflowStepInvocation before WorkflowInstance. The shared
        # "conversation_created_pilot" WorkflowDefinition itself is
        # NEVER deleted here - it is a real, permanent, platform-wide
        # artifact, not test-scoped state.
        instance_ids = select(WorkflowInstance.id).where(WorkflowInstance.company_profile_id == self.company_profile.id)
        event_ids = select(Event.id).where(Event.company_profile_id == self.company_profile.id)

        self.db.query(WorkflowStepInvocation).filter(WorkflowStepInvocation.workflow_instance_id.in_(instance_ids)).delete(
            synchronize_session=False
        )
        self.db.commit()

        from sqlalchemy import or_

        self.db.query(EventConsumption).filter(
            or_(EventConsumption.event_id.in_(event_ids), EventConsumption.workflow_instance_id.in_(instance_ids))
        ).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(WorkflowInstance).filter(WorkflowInstance.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        # Conversation deletion cascades EmailMessage/ConversationParticipant
        # (ondelete=CASCADE, migration 0009) - see test_thread_builder.py's
        # own teardown for the identical precedent.
        from app.models.conversation import Conversation

        self.db.query(Conversation).filter(Conversation.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(EmailMessage).filter(EmailMessage.provider_connection_id == self.connection.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(Event).filter(Event.company_profile_id == self.company_profile.id).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(ProviderConnection).filter(ProviderConnection.id == self.connection.id).delete()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    def _make_inbound_message(self, **overrides) -> EmailMessage:
        kwargs = dict(
            conversation_id=None,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            provider="outlook",
            direction=MessageDirection.INBOUND,
            internet_message_id=f"<{uuid.uuid4()}@example.com>",
            from_email="pilot-e2e-stranger@example.com",
            subject=f"Pilot e2e {uuid.uuid4()}",
            sent_at=_now(),
            received_at=_now(),
            synced_at=_now(),
        )
        kwargs.update(overrides)
        message = EmailMessage(**kwargs)
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    # --- the reference end-to-end path --------------------------------------
    def test_conversation_created_flows_through_full_pilot_pipeline(self):
        message = self._make_inbound_message()

        outcome = thread_builder.process_one_message(self.db, message)
        self.assertEqual(outcome, "created")
        self.db.refresh(message)
        conversation_id = message.conversation_id
        self.assertIsNotNone(conversation_id)

        # 1. Event stored, atomically with the Conversation write.
        event = self.db.scalars(
            select(Event).where(Event.subject_id == conversation_id, Event.event_type == CONVERSATION_CREATED_EVENT_TYPE)
        ).one()
        self.assertEqual(event.company_profile_id, self.company_profile.id)
        self.assertEqual(event.source, "reply_intelligence")
        self.assertEqual(event.subject_type, "conversation")

        # 2. Event Dispatcher: matches the ACTIVE pilot definition, starts
        # a new WorkflowInstance pinned to it.
        event_dispatcher_worker.run_one_tick()

        consumption = self.db.scalars(select(EventConsumption).where(EventConsumption.event_id == event.id)).one()
        self.assertIsNotNone(consumption.workflow_instance_id, "conversation.created must match the ACTIVE pilot definition")

        instance = self.db.get(WorkflowInstance, consumption.workflow_instance_id)
        self.assertEqual(instance.subject_id, conversation_id)
        self.assertEqual(instance.company_profile_id, self.company_profile.id)
        self.assertEqual(instance.status, WorkflowInstanceStatus.RUNNING, "the Step Runner has not run yet")

        # 3. Step Runner: invokes the real, registered pilot Action.
        step_runner_worker.run_one_tick()

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.COMPLETED)
        self.assertIsNotNone(instance.completed_at)

        invocation = self.db.scalars(
            select(WorkflowStepInvocation).where(WorkflowStepInvocation.workflow_instance_id == instance.id)
        ).one()
        self.assertEqual(invocation.status, WorkflowStepInvocationStatus.SUCCEEDED)
        self.assertEqual(invocation.action_key, RECORD_EXECUTION_ACTION_KEY)
        self.assertEqual(invocation.output.get("action_key"), RECORD_EXECUTION_ACTION_KEY)
        self.assertEqual(invocation.output.get("workflow_instance_id"), str(instance.id))

    # --- the negative case that makes the design meaningful -----------------
    def test_matched_conversation_does_not_publish_conversation_created(self):
        existing = self._make_inbound_message(provider_thread_id="pilot-e2e-existing-thread")
        outcome = thread_builder.process_one_message(self.db, existing)
        self.assertEqual(outcome, "created")
        self.db.refresh(existing)
        conversation_id = existing.conversation_id

        # Drain the Event this first (legitimately "created") message
        # published, so the count assertion below is scoped to only the
        # SECOND message's own behavior.
        first_event_count = (
            self.db.query(Event).filter(Event.subject_id == conversation_id, Event.event_type == CONVERSATION_CREATED_EVENT_TYPE).count()
        )
        self.assertEqual(first_event_count, 1)

        reply = self._make_inbound_message(provider_thread_id="pilot-e2e-existing-thread")
        outcome = thread_builder.process_one_message(self.db, reply)
        self.assertEqual(outcome, "matched")
        self.db.refresh(reply)
        self.assertEqual(reply.conversation_id, conversation_id, "the reply must attach to the SAME conversation, not a new one")

        # No SECOND conversation.created event for this conversation - the
        # "matched" branch must never fire the event, only "created" does.
        total_events_for_conversation = (
            self.db.query(Event).filter(Event.subject_id == conversation_id, Event.event_type == CONVERSATION_CREATED_EVENT_TYPE).count()
        )
        self.assertEqual(total_events_for_conversation, 1, "a matched (reused) conversation must never publish a second conversation.created")


if __name__ == "__main__":
    unittest.main()
