"""
End-to-end verification of M8.14's Personalization -> M7 Workflow Engine
wiring - exact structural mirror of test_discovery_workflow_e2e.py (M8.8)
and test_research_workflow_e2e.py (M8.13). Proves the real production
path for Personalization specifically:

    real run_personalization_request_endpoint() route function call
        -> real publish_event("personalization_request.run_requested",
           actor_type="user", actor_id=str(current_user.id))
        -> Event stored (transactional outbox)
        -> real Event Dispatcher tick
        -> real WorkflowInstance created, pinned to the REAL activated
           "personalization_request_execution" WorkflowDefinition
        -> real Step Runner tick
        -> real, registered PersonalizationExecutionAction actually invoked
        -> resolves the triggering user via EventConsumption -> Event.actor_id
        -> runs the REAL app.personalization.pipeline.run_personalization_request()
        -> WorkflowInstance COMPLETED, PersonalizationJob COMPLETED with a
           real, deterministic strategy_count (the engine's FALLBACK
           strategy is always produced, even with zero signals/
           recommendations/snapshot - see
           app/personalization/engine/deterministic_stub.py), and real
           personalization_job.progress events published (job-created +
           job-completed - no provider fan-out exists for this domain, so
           exactly two, never a fabricated third).

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access (same disclosed limitation as the other
two workflow e2e tests).

Run standalone with:
    python -m unittest tests.test_personalization_workflow_e2e
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
from app.models.communication_strategy import CommunicationStrategy
from app.models.company_profile import CompanyProfile
from app.models.enums import PersonalizationJobStatus, ProspectStatus, UserRole, WorkflowInstanceStatus, WorkflowStepInvocationStatus
from app.models.event_consumption import EventConsumption
from app.models.personalization_evidence import PersonalizationEvidence
from app.models.personalization_job import PersonalizationJob
from app.models.personalization_request import PersonalizationRequest
from app.models.personalization_run import PersonalizationRun
from app.models.personalization_snapshot import PersonalizationSnapshot
from app.models.personalization_strategy import PersonalizationStrategy
from app.models.personalization_template import PersonalizationTemplate
from app.models.prospect import Prospect
from app.models.user import User
from app.models.workflow_event import Event
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step_invocation import WorkflowStepInvocation

# Real production imports - deliberately not synthetic/faked.
import app.workflow_actions  # noqa: F401  (registers PERSONALIZATION_EXECUTION_ACTION_KEY for real)
from app.api.routes.personalization_requests import run_personalization_request_endpoint
from app.personalization.pipeline import PERSONALIZATION_REQUEST_RUN_REQUESTED_EVENT_TYPE
from app.workflow_bootstrap import activate_builtin_workflows
from app.workflow_engine import event_dispatcher_worker, step_runner_worker


def _now():
    return datetime.now(timezone.utc)


class TestPersonalizationWorkflowEndToEnd(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        activate_builtin_workflows(self.db)

        self.user = User(email=f"m8.11-personalization-e2e-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M8.14 Personalization E2E Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.flush()

        self.prospect = Prospect(
            company_profile_id=self.company_profile.id,
            name="Acme Corp",
            status=ProspectStatus.NEW,
            first_discovered_at=_now(),
            last_seen_at=_now(),
        )
        self.db.add(self.prospect)
        self.db.flush()

        self.personalization_template = PersonalizationTemplate(
            company_profile_id=self.company_profile.id,
            name="M8.14 e2e template",
            personalization_spec={},
            is_system_default=False,
        )
        self.db.add(self.personalization_template)
        self.db.flush()

        self.request = PersonalizationRequest(
            prospect_id=self.prospect.id,
            company_profile_id=self.company_profile.id,
            personalization_template_id=self.personalization_template.id,
            requested_by_user_id=self.user.id,
        )
        self.db.add(self.request)
        self.db.commit()

    def tearDown(self):
        self.db.rollback()

        instance_ids = select(WorkflowInstance.id).where(WorkflowInstance.company_profile_id == self.company_profile.id)
        event_ids = select(Event.id).where(Event.company_profile_id == self.company_profile.id)
        snapshot_ids = select(PersonalizationSnapshot.id).where(PersonalizationSnapshot.prospect_id == self.prospect.id)
        strategy_ids = select(PersonalizationStrategy.id).where(PersonalizationStrategy.personalization_snapshot_id.in_(snapshot_ids))

        self.db.query(WorkflowStepInvocation).filter(WorkflowStepInvocation.workflow_instance_id.in_(instance_ids)).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(EventConsumption).filter(
            or_(EventConsumption.event_id.in_(event_ids), EventConsumption.workflow_instance_id.in_(instance_ids))
        ).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(WorkflowInstance).filter(WorkflowInstance.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(PersonalizationEvidence).filter(PersonalizationEvidence.personalization_strategy_id.in_(strategy_ids)).delete(
            synchronize_session=False
        )
        self.db.query(PersonalizationStrategy).filter(PersonalizationStrategy.personalization_snapshot_id.in_(snapshot_ids)).delete(
            synchronize_session=False
        )
        self.db.query(CommunicationStrategy).filter(CommunicationStrategy.personalization_snapshot_id.in_(snapshot_ids)).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(PersonalizationSnapshot).filter(PersonalizationSnapshot.prospect_id == self.prospect.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(PersonalizationRun).filter(PersonalizationRun.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(PersonalizationJob).filter(PersonalizationJob.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(PersonalizationRequest).filter(PersonalizationRequest.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.query(PersonalizationTemplate).filter(PersonalizationTemplate.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(Prospect).filter(Prospect.company_profile_id == self.company_profile.id).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(Event).filter(Event.company_profile_id == self.company_profile.id).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    # --- the reference end-to-end path --------------------------------------
    def test_personalization_request_run_flows_through_full_workflow_pipeline(self):
        # 1. The real route function.
        result = run_personalization_request_endpoint(
            prospect_id=self.prospect.id,
            request_id=self.request.id,
            run_in=None,
            profile=self.company_profile,
            current_user=self.user,
            db=self.db,
        )
        self.assertEqual(result.status, "queued")
        self.assertEqual(result.personalization_request_id, self.request.id)

        event = self.db.scalars(
            select(Event).where(
                Event.subject_id == self.request.id, Event.event_type == PERSONALIZATION_REQUEST_RUN_REQUESTED_EVENT_TYPE
            )
        ).one()
        self.assertEqual(event.company_profile_id, self.company_profile.id)
        self.assertEqual(event.actor_type, "user")
        self.assertEqual(event.actor_id, str(self.user.id))

        # 2. Event Dispatcher: matches the ACTIVE
        # personalization_request_execution definition, starts a new
        # WorkflowInstance pinned to it.
        event_dispatcher_worker.run_one_tick()

        consumption = self.db.scalars(select(EventConsumption).where(EventConsumption.event_id == event.id)).one()
        self.assertIsNotNone(
            consumption.workflow_instance_id,
            "personalization_request.run_requested must match the ACTIVE personalization_request_execution definition",
        )

        instance = self.db.get(WorkflowInstance, consumption.workflow_instance_id)
        self.assertEqual(instance.subject_type, "personalization_request")
        self.assertEqual(instance.subject_id, self.request.id)
        self.assertEqual(instance.company_profile_id, self.company_profile.id)
        self.assertEqual(instance.status, WorkflowInstanceStatus.RUNNING, "the Step Runner has not run yet")

        # 3. Step Runner: invokes the real, registered PersonalizationExecutionAction.
        step_runner_worker.run_one_tick()

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.COMPLETED)
        self.assertIsNotNone(instance.completed_at)

        invocation = self.db.scalars(
            select(WorkflowStepInvocation).where(WorkflowStepInvocation.workflow_instance_id == instance.id)
        ).one()
        self.assertEqual(invocation.status, WorkflowStepInvocationStatus.SUCCEEDED)
        self.assertIn("personalization_job_id", invocation.output)

        # 4. The real PersonalizationJob the Action actually ran.
        job = self.db.get(PersonalizationJob, uuid.UUID(invocation.output["personalization_job_id"]))
        self.assertIsNotNone(job)
        self.assertEqual(job.personalization_request_id, self.request.id)
        self.assertEqual(job.status, PersonalizationJobStatus.COMPLETED)
        self.assertEqual(
            job.strategy_count, 2, "PRIMARY (fallback text, no recommendations exist) + FALLBACK is always produced"
        )

        snapshot = self.db.scalars(
            select(PersonalizationSnapshot).where(PersonalizationSnapshot.prospect_id == self.prospect.id)
        ).one()
        self.assertEqual(snapshot.version, 1)
        self.assertTrue(snapshot.is_current)

        # 5. Real progress events were published - job-created + job-completed
        # only (no provider fan-out exists for this domain - see
        # app.personalization.pipeline's own docstring on why a fabricated
        # third event would violate Principle 1).
        progress_events = list(
            self.db.scalars(
                select(Event).where(Event.subject_id == job.id, Event.event_type == "personalization_job.progress")
            ).all()
        )
        self.assertEqual(len(progress_events), 2, "exactly job-created + job-completed, no fabricated intermediate stage")


if __name__ == "__main__":
    unittest.main()
