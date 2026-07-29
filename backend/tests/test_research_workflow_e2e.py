"""
End-to-end verification of M8.13's Research -> M7 Workflow Engine wiring -
exact structural mirror of test_discovery_workflow_e2e.py (M8.8), itself
built on test_pilot_workflow_e2e.py's reference pattern. Proves the real
production path for Research specifically:

    real run_research_request_endpoint() route function call
        -> real publish_event("research_request.run_requested",
           actor_type="user", actor_id=str(current_user.id),
           payload={"run_input": {...}})
        -> Event stored (transactional outbox)
        -> real Event Dispatcher tick
        -> real WorkflowInstance created, pinned to the REAL activated
           "research_request_execution" WorkflowDefinition
        -> real Step Runner tick
        -> real, registered ResearchExecutionAction actually invoked
        -> resolves the triggering user AND run_input via
           EventConsumption -> Event.actor_id / Event.payload
        -> runs the REAL app.research.pipeline.run_research_request()
           against a real ManualDocumentProvider document
        -> WorkflowInstance COMPLETED, ResearchJob COMPLETED, a real
           Signal detected (deterministic keyword match), and real
           research_job.progress events published incrementally

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access (same disclosed limitation as
test_pilot_workflow_e2e.py / test_discovery_workflow_e2e.py).

Run standalone with:
    python -m unittest tests.test_research_workflow_e2e
"""
import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.ai_analysis import AIAnalysis
from app.models.company_profile import CompanyProfile
from app.models.enums import (
    ProspectStatus,
    ResearchJobStatus,
    UserRole,
    WorkflowInstanceStatus,
    WorkflowStepInvocationStatus,
)
from app.models.event_consumption import EventConsumption
from app.models.intelligence_snapshot import IntelligenceSnapshot
from app.models.prospect import Prospect
from app.models.raw_document import RawDocument
from app.models.recommendation import Recommendation
from app.models.research_job import ResearchJob
from app.models.research_job_provider_run import ResearchJobProviderRun
from app.models.research_request import ResearchRequest
from app.models.research_run import ResearchRun
from app.models.research_source import ResearchSource
from app.models.research_template import ResearchTemplate
from app.models.signal import Signal
from app.models.user import User
from app.models.workflow_event import Event
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step_invocation import WorkflowStepInvocation
from tests.event_backbone_cleanup import delete_events_and_dependents

# Real production imports - deliberately not synthetic/faked.
import app.workflow_actions  # noqa: F401  (registers RESEARCH_EXECUTION_ACTION_KEY for real)
from app.api.routes.research_requests import run_research_request_endpoint
from app.research.pipeline import RESEARCH_REQUEST_RUN_REQUESTED_EVENT_TYPE
from app.schemas.research_request import ResearchRequestRunBody
from app.workflow_bootstrap import activate_builtin_workflows
from app.workflow_engine import event_dispatcher_worker, step_runner_worker


def _now():
    return datetime.now(timezone.utc)


class TestResearchWorkflowEndToEnd(unittest.TestCase):
    def setUp(self):
        # This test's whole point (see module docstring) is proving the
        # deterministic keyword-match Signal-detection path end to end -
        # it never asserted RESEARCH_ANALYSIS_ENGINE_BACKEND explicitly
        # because "deterministic" used to be the global default anyway.
        # Now that the CEO has approved flipping that default to "llm"
        # (the M11 AI Gateway/Agent-backed engine, which would attempt a
        # real provider call here), this test pins its own backend
        # explicitly so it keeps testing exactly what its docstring says
        # it tests, independent of whatever the global default is.
        self._original_backend = settings.RESEARCH_ANALYSIS_ENGINE_BACKEND
        settings.RESEARCH_ANALYSIS_ENGINE_BACKEND = "deterministic"

        self.db = SessionLocal()

        # Real bootstrap - idempotent, exactly what app.main's lifespan()
        # does on every real boot.
        activate_builtin_workflows(self.db)

        self.user = User(email=f"m8.10-research-e2e-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M8.13 Research E2E Test Co", is_default=False)
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

        self.research_template = ResearchTemplate(
            company_profile_id=self.company_profile.id, name="M8.13 e2e template", research_spec={}, is_system_default=False
        )
        self.db.add(self.research_template)
        self.db.flush()

        self.request = ResearchRequest(
            prospect_id=self.prospect.id,
            company_profile_id=self.company_profile.id,
            research_template_id=self.research_template.id,
            requested_by_user_id=self.user.id,
        )
        self.db.add(self.request)
        self.db.commit()

    def tearDown(self):
        settings.RESEARCH_ANALYSIS_ENGINE_BACKEND = self._original_backend

        self.db.rollback()

        instance_ids = select(WorkflowInstance.id).where(WorkflowInstance.company_profile_id == self.company_profile.id)
        event_ids = select(Event.id).where(Event.company_profile_id == self.company_profile.id)
        job_ids = select(ResearchJob.id).where(ResearchJob.company_profile_id == self.company_profile.id)
        source_ids = select(ResearchSource.id).where(ResearchSource.research_job_id.in_(job_ids))
        snapshot_ids = select(IntelligenceSnapshot.id).where(IntelligenceSnapshot.prospect_id == self.prospect.id)

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

        self.db.query(Signal).filter(Signal.intelligence_snapshot_id.in_(snapshot_ids)).delete(synchronize_session=False)
        self.db.query(Recommendation).filter(Recommendation.intelligence_snapshot_id.in_(snapshot_ids)).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(AIAnalysis).filter(AIAnalysis.prospect_id == self.prospect.id).delete(synchronize_session=False)
        self.db.query(IntelligenceSnapshot).filter(IntelligenceSnapshot.prospect_id == self.prospect.id).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(RawDocument).filter(RawDocument.research_source_id.in_(source_ids)).delete(synchronize_session=False)
        self.db.query(ResearchSource).filter(ResearchSource.research_job_id.in_(job_ids)).delete(synchronize_session=False)
        self.db.query(ResearchJobProviderRun).filter(ResearchJobProviderRun.research_job_id.in_(job_ids)).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(ResearchRun).filter(ResearchRun.company_profile_id == self.company_profile.id).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(ResearchJob).filter(ResearchJob.company_profile_id == self.company_profile.id).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(ResearchRequest).filter(ResearchRequest.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.query(ResearchTemplate).filter(ResearchTemplate.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(Prospect).filter(Prospect.company_profile_id == self.company_profile.id).delete(synchronize_session=False)
        self.db.commit()

        # Generalized fix (CEO review, 2026-07-28): a plain `DELETE FROM
        # events` here raced against this project's real, always-on
        # event_dispatcher_worker/step_runner_worker/notification worker
        # containers, which consume `events` independently of this test's
        # own explicit run_one_tick() calls - one of them can insert a
        # NotificationDispatch (or Notification) row referencing one of
        # this test's Events at any point after that Event was created.
        # NotificationDispatch/Notification are intentionally INDEPENDENT
        # consumers of Event (ondelete=RESTRICT on both - see
        # app.models.notification's own docstrings and this project's
        # standing "archive-over-delete / RESTRICT-not-CASCADE"
        # convention), so the fix is cleanup order, not a schema change:
        # delete every row with a live FK to events.id (EventConsumption,
        # Notification, NotificationDispatch - the complete set, see
        # tests/event_backbone_cleanup.py's own docstring) before the
        # Event delete itself, as the LAST thing before touching
        # CompanyProfile/User - exactly the same helper
        # test_discovery_workflow_e2e.py's own tearDown already uses for
        # this identical race.
        delete_events_and_dependents(self.db, company_profile_id=self.company_profile.id)

        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    # --- the reference end-to-end path --------------------------------------
    def test_research_request_run_flows_through_full_workflow_pipeline(self):
        # A document that deterministically trips exactly one Signal
        # keyword group ("hiring") and zero Recommendations (no Product
        # fixtures exist) - see analysis/deterministic_stub.py.
        run_body = ResearchRequestRunBody(
            documents=[{"document_type": "pasted_text", "extracted_text": "We are hiring a new sales manager this quarter."}]
        )

        # 1. The real route function.
        result = run_research_request_endpoint(
            prospect_id=self.prospect.id,
            request_id=self.request.id,
            run_in=run_body,
            profile=self.company_profile,
            current_user=self.user,
            db=self.db,
        )
        self.assertEqual(result.status, "queued")
        self.assertEqual(result.research_request_id, self.request.id)

        event = self.db.scalars(
            select(Event).where(
                Event.subject_id == self.request.id, Event.event_type == RESEARCH_REQUEST_RUN_REQUESTED_EVENT_TYPE
            )
        ).one()
        self.assertEqual(event.company_profile_id, self.company_profile.id)
        self.assertEqual(event.actor_type, "user")
        self.assertEqual(event.actor_id, str(self.user.id))
        self.assertIn("run_input", event.payload)

        # 2. Event Dispatcher: matches the ACTIVE research_request_execution
        # definition, starts a new WorkflowInstance pinned to it.
        event_dispatcher_worker.run_one_tick()

        consumption = self.db.scalars(select(EventConsumption).where(EventConsumption.event_id == event.id)).one()
        self.assertIsNotNone(
            consumption.workflow_instance_id, "research_request.run_requested must match the ACTIVE research_request_execution definition"
        )

        instance = self.db.get(WorkflowInstance, consumption.workflow_instance_id)
        self.assertEqual(instance.subject_type, "research_request")
        self.assertEqual(instance.subject_id, self.request.id)
        self.assertEqual(instance.company_profile_id, self.company_profile.id)
        self.assertEqual(instance.status, WorkflowInstanceStatus.RUNNING, "the Step Runner has not run yet")

        # 3. Step Runner: invokes the real, registered ResearchExecutionAction.
        step_runner_worker.run_one_tick()

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.COMPLETED)
        self.assertIsNotNone(instance.completed_at)

        invocation = self.db.scalars(
            select(WorkflowStepInvocation).where(WorkflowStepInvocation.workflow_instance_id == instance.id)
        ).one()
        self.assertEqual(invocation.status, WorkflowStepInvocationStatus.SUCCEEDED)
        self.assertIn("research_job_id", invocation.output)

        # 4. The real ResearchJob the Action actually ran, with real,
        # incrementally-committed state - not fabricated.
        job = self.db.get(ResearchJob, uuid.UUID(invocation.output["research_job_id"]))
        self.assertIsNotNone(job)
        self.assertEqual(job.research_request_id, self.request.id)
        self.assertEqual(job.status, ResearchJobStatus.COMPLETED)
        self.assertEqual(job.sources_used, ["manual_document"])
        self.assertEqual(job.raw_document_count, 1)
        self.assertEqual(job.signal_count, 1, "the 'hiring' keyword must deterministically trip exactly one Signal")
        self.assertEqual(job.recommendation_count, 0, "no Product fixtures exist, so zero Recommendations is correct")

        provider_run = self.db.scalars(
            select(ResearchJobProviderRun).where(ResearchJobProviderRun.research_job_id == job.id)
        ).one()
        self.assertEqual(provider_run.provider_key, "manual_document")
        self.assertEqual(provider_run.status, "completed")

        signal = self.db.scalars(select(Signal).where(Signal.prospect_id == self.prospect.id)).one()
        self.assertEqual(signal.signal_type, "hiring")

        # 5. Real progress events were published incrementally along the
        # way - job-created + per-provider + job-completed.
        progress_event_count = (
            self.db.query(Event).filter(Event.subject_id == job.id, Event.event_type == "research_job.progress").count()
        )
        self.assertGreaterEqual(progress_event_count, 3, "expected job-created + per-provider + job-completed progress events")

    # --- the negative case that makes the async wiring meaningful ----------
    def test_unknown_provider_completes_the_action_but_fails_the_domain_job(self):
        """
        A subtle, real distinction the M7 engine makes deliberately (see
        SupervisorInvocationAction's own docstring on ActionOutcome vs.
        domain-level outcomes): run_research_request() does NOT raise for
        an unknown provider_key - it catches the KeyError internally and
        records a FAILED ResearchJob, then returns normally. So
        ResearchExecutionAction.execute() returns ActionOutcome.SUCCESS
        (the Action itself did not fail - it successfully ran a job that
        happened to fail), and the WorkflowInstance reaches COMPLETED, NOT
        FAILED. A consumer must read the domain ResearchJob's own status
        field for the real outcome - WorkflowInstance.status alone is not
        enough. This is exactly the same relationship Discovery's engine
        wiring has, just exercised here for real with a genuinely unknown
        provider_key instead of asserted from documentation.
        """
        run_body = ResearchRequestRunBody(source_types=["totally_unknown_provider"], documents=[])

        run_research_request_endpoint(
            prospect_id=self.prospect.id,
            request_id=self.request.id,
            run_in=run_body,
            profile=self.company_profile,
            current_user=self.user,
            db=self.db,
        )
        event = self.db.scalars(
            select(Event).where(
                Event.subject_id == self.request.id, Event.event_type == RESEARCH_REQUEST_RUN_REQUESTED_EVENT_TYPE
            )
        ).one()

        event_dispatcher_worker.run_one_tick()
        consumption = self.db.scalars(select(EventConsumption).where(EventConsumption.event_id == event.id)).one()
        instance = self.db.get(WorkflowInstance, consumption.workflow_instance_id)

        step_runner_worker.run_one_tick()
        self.db.refresh(instance)

        self.assertEqual(instance.status, WorkflowInstanceStatus.COMPLETED, "the Action itself did not fail")

        invocation = self.db.scalars(
            select(WorkflowStepInvocation).where(WorkflowStepInvocation.workflow_instance_id == instance.id)
        ).one()
        job = self.db.get(ResearchJob, uuid.UUID(invocation.output["research_job_id"]))
        self.assertEqual(job.status, ResearchJobStatus.FAILED, "the domain job itself must show the real failure")
        self.assertIn("Unknown research provider", job.error_message or "")


if __name__ == "__main__":
    unittest.main()
