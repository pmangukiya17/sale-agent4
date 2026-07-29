"""
End-to-end verification of M8.15's Outreach -> M7 Workflow Engine wiring -
exact structural mirror of test_personalization_workflow_e2e.py (M8.14),
test_research_workflow_e2e.py (M8.13), and test_discovery_workflow_e2e.py
(M8.8). Proves the real production path for Outreach specifically:

    real run_outreach_request_endpoint() route function call
        -> real publish_event("outreach_request.run_requested",
           actor_type="user", actor_id=str(current_user.id))
        -> Event stored (transactional outbox)
        -> real Event Dispatcher tick
        -> real WorkflowInstance created, pinned to the REAL activated
           "outreach_request_execution" WorkflowDefinition
        -> real Step Runner tick
        -> real, registered OutreachExecutionAction actually invoked
        -> resolves the triggering user via EventConsumption -> Event.actor_id
        -> runs the REAL app.outreach.pipeline.run_outreach_request()
        -> WorkflowInstance COMPLETED, OutreachJob COMPLETED with a real,
           deterministic block_count (two FIXED playbook blocks - FIXED
           content is copied verbatim by EmailChannelProvider regardless of
           whether any PersonalizationSnapshot/strategies exist, so the
           count is deterministic without seeding any Personalization
           fixtures), and real outreach_job.progress events published
           (job-created + job-completed - no provider fan-out exists for
           this domain, never a fabricated third).

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access (same disclosed limitation as the other
three workflow e2e tests).

Run standalone with:
    python -m unittest tests.test_outreach_workflow_e2e
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
from app.models.enums import (
    OutreachBlockBehavior,
    OutreachJobStatus,
    ProspectStatus,
    UserRole,
    WorkflowInstanceStatus,
    WorkflowStepInvocationStatus,
)
from app.models.event_consumption import EventConsumption
from app.models.outreach_block import OutreachBlock
from app.models.outreach_draft import OutreachDraft
from app.models.outreach_edit import OutreachEdit
from app.models.outreach_evidence import OutreachEvidence
from app.models.outreach_job import OutreachJob
from app.models.outreach_playbook import OutreachPlaybook
from app.models.outreach_request import OutreachRequest
from app.models.outreach_run import OutreachRun
from app.models.prompt_version import PromptVersion
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.user import User
from app.models.workflow_event import Event
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step_invocation import WorkflowStepInvocation
from tests.event_backbone_cleanup import delete_events_and_dependents

# Real production imports - deliberately not synthetic/faked.
import app.workflow_actions  # noqa: F401  (registers OUTREACH_EXECUTION_ACTION_KEY for real)
from app.api.routes.outreach_requests import run_outreach_request_endpoint
from app.outreach.pipeline import OUTREACH_REQUEST_RUN_REQUESTED_EVENT_TYPE
from app.workflow_bootstrap import activate_builtin_workflows
from app.workflow_engine import event_dispatcher_worker, step_runner_worker


def _now():
    return datetime.now(timezone.utc)


class TestOutreachWorkflowEndToEnd(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        activate_builtin_workflows(self.db)

        self.user = User(email=f"m8.12-outreach-e2e-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M8.15 Outreach E2E Test Co", is_default=False)
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

        self.contact = ProspectContact(prospect_id=self.prospect.id, name="Jane Buyer", role="VP Procurement")
        self.db.add(self.contact)
        self.db.flush()

        # A system-default active PromptVersion for channel "email" -
        # _resolve_prompt_version() raises OutreachConfigError without one,
        # a genuine config-error path, not something this happy-path test
        # exercises.
        self.prompt_version = PromptVersion(
            company_profile_id=None,
            channel_key="email",
            prompt_key="email_generation",
            version=1,
            prompt_text="Write a concise, evidence-anchored B2B email. Never invent facts.",
            is_active=True,
        )
        self.db.add(self.prompt_version)

        self.outreach_playbook = OutreachPlaybook(
            company_profile_id=self.company_profile.id,
            name="M8.15 e2e playbook",
            version=1,
            is_current=True,
            is_system_default=False,
        )
        self.db.add(self.outreach_playbook)
        self.db.flush()

        # Two FIXED blocks - deterministic, evidence-independent content
        # EmailChannelProvider copies verbatim regardless of whether any
        # PersonalizationSnapshot/strategy exists - the same reasoning
        # test_personalization_workflow_e2e.py used for its own
        # deterministic strategy_count assertion.
        self.db.add(
            OutreachBlock(
                outreach_playbook_id=self.outreach_playbook.id,
                block_key="greeting",
                behavior=OutreachBlockBehavior.FIXED,
                fixed_content="Hi {{buyer}},",
                display_order=0,
            )
        )
        self.db.add(
            OutreachBlock(
                outreach_playbook_id=self.outreach_playbook.id,
                block_key="signature",
                behavior=OutreachBlockBehavior.FIXED,
                fixed_content="Best,\n{{company}}",
                display_order=1,
            )
        )
        self.db.flush()

        self.request = OutreachRequest(
            prospect_id=self.prospect.id,
            prospect_contact_id=self.contact.id,
            company_profile_id=self.company_profile.id,
            outreach_playbook_id=self.outreach_playbook.id,
            channel_key="email",
            requested_by_user_id=self.user.id,
        )
        self.db.add(self.request)
        self.db.commit()

    def tearDown(self):
        self.db.rollback()

        instance_ids = select(WorkflowInstance.id).where(WorkflowInstance.company_profile_id == self.company_profile.id)
        event_ids = select(Event.id).where(Event.company_profile_id == self.company_profile.id)
        draft_ids = select(OutreachDraft.id).where(OutreachDraft.company_profile_id == self.company_profile.id)

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

        self.db.query(OutreachEvidence).filter(OutreachEvidence.outreach_draft_id.in_(draft_ids)).delete(
            synchronize_session=False
        )
        self.db.query(OutreachEdit).filter(OutreachEdit.outreach_draft_id.in_(draft_ids)).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(OutreachDraft).filter(OutreachDraft.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(OutreachRun).filter(OutreachRun.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(OutreachJob).filter(OutreachJob.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(OutreachRequest).filter(OutreachRequest.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.query(OutreachBlock).filter(OutreachBlock.outreach_playbook_id == self.outreach_playbook.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        self.db.query(OutreachPlaybook).filter(OutreachPlaybook.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.query(PromptVersion).filter(PromptVersion.id == self.prompt_version.id).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(ProspectContact).filter(ProspectContact.prospect_id == self.prospect.id).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(Prospect).filter(Prospect.company_profile_id == self.company_profile.id).delete(synchronize_session=False)
        self.db.commit()

        # Generalized fix (CEO review, 2026-07-28 - see
        # test_research_workflow_e2e.py's own tearDown for the full
        # writeup of this identical race): NotificationDispatch/
        # Notification are intentionally independent, RESTRICT-FK'd
        # consumers of Event, and this project's real, always-on
        # notification worker can insert one referencing this test's own
        # Events at any time - delete the complete dependent set
        # (EventConsumption/Notification/NotificationDispatch) before the
        # Event delete itself, as the LAST thing before touching
        # CompanyProfile/User.
        delete_events_and_dependents(self.db, company_profile_id=self.company_profile.id)

        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    # --- the reference end-to-end path --------------------------------------
    def test_outreach_request_run_flows_through_full_workflow_pipeline(self):
        # 1. The real route function.
        result = run_outreach_request_endpoint(
            prospect_id=self.prospect.id,
            contact_id=self.contact.id,
            request_id=self.request.id,
            run_in=None,
            profile=self.company_profile,
            current_user=self.user,
            db=self.db,
        )
        self.assertEqual(result.status, "queued")
        self.assertEqual(result.outreach_request_id, self.request.id)

        event = self.db.scalars(
            select(Event).where(Event.subject_id == self.request.id, Event.event_type == OUTREACH_REQUEST_RUN_REQUESTED_EVENT_TYPE)
        ).one()
        self.assertEqual(event.company_profile_id, self.company_profile.id)
        self.assertEqual(event.actor_type, "user")
        self.assertEqual(event.actor_id, str(self.user.id))

        # 2. Event Dispatcher: matches the ACTIVE outreach_request_execution
        # definition, starts a new WorkflowInstance pinned to it.
        event_dispatcher_worker.run_one_tick()

        consumption = self.db.scalars(select(EventConsumption).where(EventConsumption.event_id == event.id)).one()
        self.assertIsNotNone(
            consumption.workflow_instance_id,
            "outreach_request.run_requested must match the ACTIVE outreach_request_execution definition",
        )

        instance = self.db.get(WorkflowInstance, consumption.workflow_instance_id)
        self.assertEqual(instance.subject_type, "outreach_request")
        self.assertEqual(instance.subject_id, self.request.id)
        self.assertEqual(instance.company_profile_id, self.company_profile.id)
        self.assertEqual(instance.status, WorkflowInstanceStatus.RUNNING, "the Step Runner has not run yet")

        # 3. Step Runner: invokes the real, registered OutreachExecutionAction.
        step_runner_worker.run_one_tick()

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.COMPLETED)
        self.assertIsNotNone(instance.completed_at)

        invocation = self.db.scalars(
            select(WorkflowStepInvocation).where(WorkflowStepInvocation.workflow_instance_id == instance.id)
        ).one()
        self.assertEqual(invocation.status, WorkflowStepInvocationStatus.SUCCEEDED)
        self.assertIn("outreach_job_id", invocation.output)

        # 4. The real OutreachJob the Action actually ran.
        job = self.db.get(OutreachJob, uuid.UUID(invocation.output["outreach_job_id"]))
        self.assertIsNotNone(job)
        self.assertEqual(job.outreach_request_id, self.request.id)
        self.assertEqual(job.status, OutreachJobStatus.COMPLETED)
        self.assertEqual(job.block_count, 2, "the playbook's two FIXED blocks are rendered regardless of strategy availability")

        draft = self.db.scalars(select(OutreachDraft).where(OutreachDraft.outreach_job_id == job.id)).one()
        self.assertEqual(draft.version, 1)
        self.assertTrue(draft.is_current)

        # 5. Real progress events were published - job-created + job-completed
        # only (no provider fan-out exists for this domain).
        progress_events = list(
            self.db.scalars(select(Event).where(Event.subject_id == job.id, Event.event_type == "outreach_job.progress")).all()
        )
        self.assertEqual(len(progress_events), 2, "exactly job-created + job-completed, no fabricated intermediate stage")


if __name__ == "__main__":
    unittest.main()
