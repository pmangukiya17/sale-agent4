"""
End-to-end verification of M8.8's Discovery -> M7 Workflow Engine wiring,
built on the same reference pattern test_pilot_workflow_e2e.py established
(that file's own docstring calls itself "THE reference verification for
all future workflows") - this is the second one, proving the real
production path for Discovery specifically:

    real run_search() route function call (a real DB session, exactly how
    FastAPI would dispatch it - Depends() defaults are simply overridden
    by passing the resolved objects directly, the same shortcut this
    project's other route-level tests already use)
        -> real publish_event("discovery_search.run_requested",
           actor_type="user", actor_id=str(current_user.id))
        -> Event stored (transactional outbox)
        -> real Event Dispatcher tick
        -> real WorkflowInstance created, pinned to the REAL activated
           "discovery_search_execution" WorkflowDefinition (authored via
           app.workflow_bootstrap.activate_builtin_workflows - the same
           bootstrap app.main's own lifespan() calls on every real boot)
        -> real Step Runner tick
        -> real, registered DiscoveryExecutionAction actually invoked
        -> resolves the triggering user via EventConsumption -> Event.actor_id
        -> runs the REAL app.discovery.pipeline.run_discovery_search()
           against a real ManualCSVProvider row
        -> WorkflowInstance COMPLETED, DiscoveryJob COMPLETED, a real
           qualified Prospect, and real discovery_job.progress events
           published incrementally along the way (not one atomic write)

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access (see test_pilot_workflow_e2e.py's own
docstring for the identical caveat).

Run standalone with:
    python -m unittest tests.test_discovery_workflow_e2e
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
from app.models.discovery_job import DiscoveryJob
from app.models.discovery_job_provider_run import DiscoveryJobProviderRun
from app.models.discovery_provider_result import DiscoveryProviderResult
from app.models.discovery_run import DiscoveryRun
from app.models.discovery_search import DiscoverySearch
from app.models.enums import (
    DiscoveryJobStatus,
    ProspectStatus,
    UserRole,
    WorkflowInstanceStatus,
    WorkflowStepInvocationStatus,
)
from app.models.event_consumption import EventConsumption
from app.models.icp_criteria import ICPCriteria
from tests.event_backbone_cleanup import delete_events_and_dependents
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.prospect_source import ProspectSource
from app.models.prospect_timeline_event import ProspectTimelineEvent
from app.models.search_template import SearchTemplate
from app.models.user import User
from app.models.workflow_event import Event
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step_invocation import WorkflowStepInvocation

# Real production imports - deliberately not synthetic/faked, unlike unit
# tests elsewhere in this suite. Importing app.workflow_actions registers
# the real DiscoveryExecutionAction; activate_builtin_workflows() is the
# real bootstrap app.main's own lifespan() calls on every boot.
import app.workflow_actions  # noqa: F401  (registers DISCOVERY_EXECUTION_ACTION_KEY for real)
from app.api.routes.discovery_searches import run_search
from app.discovery.pipeline import DISCOVERY_SEARCH_RUN_REQUESTED_EVENT_TYPE, run_discovery_search
from app.workflow_bootstrap import activate_builtin_workflows
from app.workflow_engine import event_dispatcher_worker, step_runner_worker


def _now():
    return datetime.now(timezone.utc)


class TestDiscoveryWorkflowEndToEnd(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        # Real bootstrap - idempotent, exactly what app.main's lifespan()
        # does on every real boot. Registers/activates BOTH built-ins
        # (conversation_created_pilot and discovery_search_execution) if
        # this is a fresh database; a true no-op otherwise.
        activate_builtin_workflows(self.db)

        self.user = User(email=f"m8.8-discovery-e2e-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M8.8 Discovery E2E Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.flush()

        self.search_template = SearchTemplate(
            company_profile_id=self.company_profile.id, name="M8.8 e2e template", query_spec={}, is_system_default=False
        )
        self.db.add(self.search_template)
        self.db.flush()

        # minimum_confidence_score=None -> _score_and_apply's own "threshold
        # is None => qualifies" rule - a deterministic QUALIFIED outcome for
        # any created prospect, no fixture-specific scoring math required.
        self.icp = ICPCriteria(
            company_profile_id=self.company_profile.id,
            version=1,
            name="M8.8 e2e ICP",
            is_active=True,
            minimum_confidence_score=None,
        )
        self.db.add(self.icp)
        self.db.flush()

        self.search = DiscoverySearch(
            company_profile_id=self.company_profile.id,
            search_template_id=self.search_template.id,
            icp_criteria_id=self.icp.id,
            name="M8.8 e2e search",
            query_spec={"rows": [{"name": "Acme Corp", "website": "acme.example.com", "country": "United States"}]},
            provider_keys=["manual_csv"],
        )
        self.db.add(self.search)
        self.db.commit()

    def tearDown(self):
        self.db.rollback()  # discard any uncommitted state from a failed assertion mid-test

        instance_ids = select(WorkflowInstance.id).where(WorkflowInstance.company_profile_id == self.company_profile.id)
        event_ids = select(Event.id).where(Event.company_profile_id == self.company_profile.id)
        job_ids = select(DiscoveryJob.id).where(DiscoveryJob.company_profile_id == self.company_profile.id)
        prospect_ids = select(Prospect.id).where(Prospect.company_profile_id == self.company_profile.id)

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

        self.db.query(ProspectTimelineEvent).filter(ProspectTimelineEvent.prospect_id.in_(prospect_ids)).delete(
            synchronize_session=False
        )
        self.db.query(ProspectContact).filter(ProspectContact.prospect_id.in_(prospect_ids)).delete(synchronize_session=False)
        self.db.query(ProspectSource).filter(ProspectSource.prospect_id.in_(prospect_ids)).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(DiscoveryProviderResult).filter(DiscoveryProviderResult.discovery_job_id.in_(job_ids)).delete(
            synchronize_session=False
        )
        self.db.query(DiscoveryJobProviderRun).filter(DiscoveryJobProviderRun.discovery_job_id.in_(job_ids)).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(DiscoveryRun).filter(DiscoveryRun.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(DiscoveryJob).filter(DiscoveryJob.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(Prospect).filter(Prospect.company_profile_id == self.company_profile.id).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(DiscoverySearch).filter(DiscoverySearch.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.query(ICPCriteria).filter(ICPCriteria.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.query(SearchTemplate).filter(SearchTemplate.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        # Generalized fix (superseding two earlier per-table patches -
        # EventConsumption alone, then discovering Notification/
        # NotificationDispatch too): delete EVERY row with a live FK to
        # events.id (the complete set - EventConsumption, Notification,
        # NotificationDispatch - see event_backbone_cleanup.py's own
        # docstring for the full dependency graph and why this must be
        # the LAST thing before touching CompanyProfile/User to stay
        # robust against this project's real, always-on
        # event_dispatcher_worker/step_runner_worker/notification worker
        # containers, which consume `events` independently of this
        # test's own explicit run_one_tick() calls.
        delete_events_and_dependents(self.db, company_profile_id=self.company_profile.id)

        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    # --- the reference end-to-end path --------------------------------------
    def test_discovery_search_run_flows_through_full_workflow_pipeline(self):
        # 1. The real route function.
        result = run_search(search_id=self.search.id, profile=self.company_profile, current_user=self.user, db=self.db)
        self.assertEqual(result.status, "queued")
        self.assertEqual(result.discovery_search_id, self.search.id)

        event = self.db.scalars(
            select(Event).where(
                Event.subject_id == self.search.id, Event.event_type == DISCOVERY_SEARCH_RUN_REQUESTED_EVENT_TYPE
            )
        ).one()
        self.assertEqual(event.company_profile_id, self.company_profile.id)
        self.assertEqual(event.actor_type, "user")
        self.assertEqual(event.actor_id, str(self.user.id))

        # 2. Event Dispatcher: matches the ACTIVE discovery_search_execution
        # definition, starts a new WorkflowInstance pinned to it.
        event_dispatcher_worker.run_one_tick()

        consumption = self.db.scalars(select(EventConsumption).where(EventConsumption.event_id == event.id)).one()
        self.assertIsNotNone(
            consumption.workflow_instance_id, "discovery_search.run_requested must match the ACTIVE discovery_search_execution definition"
        )

        instance = self.db.get(WorkflowInstance, consumption.workflow_instance_id)
        self.assertEqual(instance.subject_type, "discovery_search")
        self.assertEqual(instance.subject_id, self.search.id)
        self.assertEqual(instance.company_profile_id, self.company_profile.id)
        self.assertEqual(instance.status, WorkflowInstanceStatus.RUNNING, "the Step Runner has not run yet")

        # 3. Step Runner: invokes the real, registered DiscoveryExecutionAction.
        step_runner_worker.run_one_tick()

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.COMPLETED)
        self.assertIsNotNone(instance.completed_at)

        invocation = self.db.scalars(
            select(WorkflowStepInvocation).where(WorkflowStepInvocation.workflow_instance_id == instance.id)
        ).one()
        self.assertEqual(invocation.status, WorkflowStepInvocationStatus.SUCCEEDED)
        self.assertIn("discovery_job_id", invocation.output)

        # 4. The real DiscoveryJob the Action actually ran, with real,
        # incrementally-committed state - not fabricated.
        job = self.db.get(DiscoveryJob, uuid.UUID(invocation.output["discovery_job_id"]))
        self.assertIsNotNone(job)
        self.assertEqual(job.discovery_search_id, self.search.id)
        self.assertEqual(job.status, DiscoveryJobStatus.COMPLETED)
        self.assertEqual(job.providers_used, ["manual_csv"])
        self.assertEqual(job.prospect_created_count, 1)
        self.assertEqual(job.prospect_qualified_count, 1, "minimum_confidence_score=None must qualify the created prospect")
        self.assertEqual(job.prospect_rejected_count, 0)

        provider_run = self.db.scalars(
            select(DiscoveryJobProviderRun).where(DiscoveryJobProviderRun.discovery_job_id == job.id)
        ).one()
        self.assertEqual(provider_run.provider_key, "manual_csv")
        self.assertEqual(provider_run.status, "completed")

        prospect = self.db.scalars(select(Prospect).where(Prospect.discovery_search_id == self.search.id)).one()
        self.assertEqual(prospect.name, "Acme Corp")
        self.assertEqual(prospect.status, ProspectStatus.QUALIFIED)

        # 5. Real progress events were published incrementally along the
        # way - proving this ran as a live, multi-step process rather than
        # one atomic write at the very end (see app.discovery.pipeline's
        # own docstring: job-created, per-provider, and job-completed).
        progress_event_count = (
            self.db.query(Event).filter(Event.subject_id == job.id, Event.event_type == "discovery_job.progress").count()
        )
        self.assertGreaterEqual(progress_event_count, 3, "expected job-created + per-provider + job-completed progress events")

    # --- the negative case that makes the async wiring meaningful ----------
    def test_run_with_no_providers_enabled_never_publishes_trigger_event(self):
        self.search.provider_keys = []
        self.db.commit()

        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            run_search(search_id=self.search.id, profile=self.company_profile, current_user=self.user, db=self.db)
        self.assertEqual(ctx.exception.status_code, 400)

        published = (
            self.db.query(Event)
            .filter(Event.subject_id == self.search.id, Event.event_type == DISCOVERY_SEARCH_RUN_REQUESTED_EVENT_TYPE)
            .count()
        )
        self.assertEqual(published, 0, "a search with no providers must never publish a run-requested event")

    # --- M2 Phase 1b: tier-1 government identifier dedup --------------------
    def test_two_rows_sharing_a_vat_number_dedupe_via_identifier_not_website(self):
        """Two manual_csv rows in the SAME job, same VAT number, no
        website in common and different-enough names that tier 2/3
        (website/fuzzy name) would NOT have caught this - proves tier 1
        (app.discovery.identifier_lookup.find_duplicate_by_identifier)
        is what makes this a re-sighting rather than two separate
        Prospects. Calls the pipeline function directly (rather than
        through the full route->event->dispatcher->step_runner chain
        the class's other tests exercise) since the workflow-engine
        wiring itself isn't what this test is verifying - see
        test_run_with_no_providers_enabled_never_publishes_trigger_event
        above for the same "call one layer down" precedent within this
        file."""
        self.search.query_spec = {
            "rows": [
                {"name": "Acme Textiles", "country": "United States", "vat_number": "DE 123 456 789"},
                {"name": "Completely Different Trading Co", "country": "United States", "vat_number": "de123456789"},
            ]
        }
        self.db.commit()

        job = run_discovery_search(self.db, self.search, self.user)

        self.assertEqual(job.prospect_created_count, 1)
        self.assertEqual(job.prospect_matched_count, 1)

        prospect = self.db.scalars(select(Prospect).where(Prospect.discovery_search_id == self.search.id)).one()
        self.assertEqual(prospect.name, "Acme Textiles", "first-seen row's name wins; second is a re-sighting")
        self.assertEqual(prospect.vat_number, "DE123456789")

        reseen_events = (
            self.db.query(ProspectTimelineEvent)
            .filter(ProspectTimelineEvent.prospect_id == prospect.id, ProspectTimelineEvent.event_type == "reseen_by_provider")
            .all()
        )
        self.assertEqual(len(reseen_events), 1)
        self.assertEqual(reseen_events[0].payload.get("matched_via"), "identifier")

    def test_identifier_match_backfills_missing_registration_number(self):
        """First run supplies only a VAT number; a second run's row
        shares that VAT number and additionally supplies a registration
        number the existing Prospect doesn't have yet - proves
        _backfill_identifier_fields() fills it in on the re-sighting
        rather than leaving it null forever."""
        self.search.query_spec = {"rows": [{"name": "Acme Textiles", "country": "United States", "vat_number": "DE123456789"}]}
        self.db.commit()
        run_discovery_search(self.db, self.search, self.user)

        self.search.query_spec = {
            "rows": [{
                "name": "Acme Textiles", "country": "United States",
                "vat_number": "DE123456789", "registration_number": "HRB99999",
            }]
        }
        self.db.commit()
        job2 = run_discovery_search(self.db, self.search, self.user)

        self.assertEqual(job2.prospect_created_count, 0)
        self.assertEqual(job2.prospect_matched_count, 1)

        prospect = self.db.scalars(select(Prospect).where(Prospect.discovery_search_id == self.search.id)).one()
        self.assertEqual(prospect.registration_number, "HRB99999")


if __name__ == "__main__":
    unittest.main()
