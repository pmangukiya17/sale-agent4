"""
tests.test_discovery_job_cancellation - M2 Phase 1c.

Discovery Job graceful cancellation - the second half of Phase 1c's
scope (the first half, Prospect -> Opportunity Import, is covered in
tests/test_opportunities_e2e.py's own TestProspectImport class).

Same conventions as tests/test_discovery_workflow_e2e.py: direct
route/pipeline function calls against a real SessionLocal, explicit
child-then-parent teardown. Requires a real database connection - not
runnable in a sandbox with no Docker/Postgres access.

The pipeline-level tests below deterministically force a mid-run
cancellation by patching app.discovery.pipeline._is_cancellation_requested
and CANCELLATION_CHECK_INTERVAL, rather than orchestrating genuine
cross-session concurrency in a single-threaded test - this exercises
run_discovery_search()'s own branching/partial-completion logic exactly
as a real concurrent cancel request would trigger it (the function reads
the same module-level check on every call site regardless of why it
returns True), without needing multiple real DB sessions racing each
other inside one test method.

Run standalone with:
    python -m unittest tests.test_discovery_job_cancellation
"""
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import select

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.api.routes.discovery_jobs import cancel_discovery_job
from app.discovery.pipeline import run_discovery_search
from app.models.company_profile import CompanyProfile
from app.models.discovery_job import DiscoveryJob
from app.models.discovery_job_provider_run import DiscoveryJobProviderRun
from app.models.discovery_provider_result import DiscoveryProviderResult
from app.models.discovery_run import DiscoveryRun
from app.models.discovery_search import DiscoverySearch
from app.models.enums import DiscoveryJobStatus, UserRole
from app.models.icp_criteria import ICPCriteria
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.prospect_source import ProspectSource
from app.models.prospect_timeline_event import ProspectTimelineEvent
from app.models.search_template import SearchTemplate
from app.models.user import User
from app.schemas.discovery_job import DiscoveryJobCancelRequest


def _now():
    return datetime.now(timezone.utc)


class DiscoveryJobCancellationTestBase(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        self.user = User(email=f"m2-1c-cancel-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M2 Phase 1c Cancel Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.flush()

        self.search_template = SearchTemplate(
            company_profile_id=self.company_profile.id, name="Phase 1c cancel template", query_spec={}, is_system_default=False
        )
        self.db.add(self.search_template)
        self.db.flush()

        self.icp = ICPCriteria(
            company_profile_id=self.company_profile.id, version=1, name="Phase 1c cancel ICP",
            is_active=True, minimum_confidence_score=None,
        )
        self.db.add(self.icp)
        self.db.flush()

        self.search = DiscoverySearch(
            company_profile_id=self.company_profile.id,
            search_template_id=self.search_template.id,
            icp_criteria_id=self.icp.id,
            name="Phase 1c cancel search",
            query_spec={"rows": []},
            provider_keys=["manual_csv"],
        )
        self.db.add(self.search)
        self.db.commit()

        self._job_ids: list[uuid.UUID] = []

    def tearDown(self):
        self.db.rollback()

        prospect_ids = select(Prospect.id).where(Prospect.company_profile_id == self.company_profile.id)
        self.db.query(ProspectTimelineEvent).filter(ProspectTimelineEvent.prospect_id.in_(prospect_ids)).delete(
            synchronize_session=False
        )
        self.db.query(ProspectContact).filter(ProspectContact.prospect_id.in_(prospect_ids)).delete(synchronize_session=False)
        self.db.query(ProspectSource).filter(ProspectSource.prospect_id.in_(prospect_ids)).delete(synchronize_session=False)
        self.db.commit()

        job_ids = select(DiscoveryJob.id).where(DiscoveryJob.company_profile_id == self.company_profile.id)
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

        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()


class TestCancelRoute(DiscoveryJobCancellationTestBase):
    """Route-level behavior, tested against a directly-constructed
    DiscoveryJob rather than a fully-run one - isolates the cancel
    endpoint's own status/idempotency/isolation logic from
    run_discovery_search's own (covered separately below and in
    tests/test_discovery_workflow_e2e.py)."""

    def _make_job(self, status: DiscoveryJobStatus) -> DiscoveryJob:
        job = DiscoveryJob(
            discovery_search_id=self.search.id,
            company_profile_id=self.company_profile.id,
            status=status,
            started_at=_now(),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        self._job_ids.append(job.id)
        return job

    def test_cancel_running_job_sets_request_fields(self):
        job = self._make_job(DiscoveryJobStatus.RUNNING)
        result = cancel_discovery_job(
            job.id, DiscoveryJobCancelRequest(reason="no longer needed"),
            profile=self.company_profile, current_user=self.user, db=self.db,
        )
        self.assertIsNotNone(result.cancel_requested_at)
        self.assertEqual(result.cancel_requested_by_user_id, self.user.id)
        # status itself is untouched by the route - only the worker
        # (run_discovery_search) is ever allowed to write CANCELLED.
        self.assertEqual(result.status, DiscoveryJobStatus.RUNNING)
        reasons = [entry.get("reason") for entry in result.log if entry.get("event") == "cancellation_requested"]
        self.assertIn("no longer needed", reasons)

    def test_cancel_is_idempotent_on_second_call(self):
        job = self._make_job(DiscoveryJobStatus.RUNNING)
        first = cancel_discovery_job(job.id, None, profile=self.company_profile, current_user=self.user, db=self.db)
        second = cancel_discovery_job(job.id, None, profile=self.company_profile, current_user=self.user, db=self.db)
        self.assertEqual(first.cancel_requested_at, second.cancel_requested_at)
        # Exactly one cancellation_requested log entry, not two.
        entries = [e for e in second.log if e.get("event") == "cancellation_requested"]
        self.assertEqual(len(entries), 1)

    def test_cancel_rejects_a_terminal_job(self):
        job = self._make_job(DiscoveryJobStatus.COMPLETED)
        with self.assertRaises(HTTPException) as ctx:
            cancel_discovery_job(job.id, None, profile=self.company_profile, current_user=self.user, db=self.db)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cancel_rejects_a_job_from_another_business(self):
        job = self._make_job(DiscoveryJobStatus.RUNNING)
        other_user = User(email=f"m2-1c-other-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(other_user)
        self.db.flush()
        other_profile = CompanyProfile(owner_user_id=other_user.id, name="Other Co", is_default=False)
        self.db.add(other_profile)
        self.db.commit()
        try:
            with self.assertRaises(HTTPException) as ctx:
                cancel_discovery_job(job.id, None, profile=other_profile, current_user=other_user, db=self.db)
            self.assertEqual(ctx.exception.status_code, 404)
        finally:
            self.db.query(CompanyProfile).filter(CompanyProfile.id == other_profile.id).delete()
            self.db.query(User).filter(User.id == other_user.id).delete()
            self.db.commit()


class TestPipelineGracefulCancellation(DiscoveryJobCancellationTestBase):
    """Forces a deterministic mid-run cancellation via patching - see
    this module's own docstring for why."""

    def test_job_stops_partway_and_preserves_already_created_prospects(self):
        self.search.query_spec = {
            "rows": [
                {"name": f"Company {i}", "country": "United States", "website": f"company{i}.example.com"}
                for i in range(6)
            ]
        }
        self.db.commit()

        call_count = {"n": 0}

        def fake_check(db, job):
            call_count["n"] += 1
            return call_count["n"] >= 3  # first two checkpoints say "carry on", third says "stop"

        with patch("app.discovery.pipeline.CANCELLATION_CHECK_INTERVAL", 1), \
             patch("app.discovery.pipeline._is_cancellation_requested", side_effect=fake_check):
            job = run_discovery_search(self.db, self.search, self.user)

        self.assertEqual(job.status, DiscoveryJobStatus.CANCELLED)
        self.assertGreater(job.prospect_created_count, 0, "at least one candidate must have been processed before the stop")
        self.assertLess(job.prospect_created_count, 6, "must not have processed every candidate - this is the whole point")

        # Whatever WAS created is genuinely persisted, not rolled back.
        created = list(
            self.db.scalars(select(Prospect).where(Prospect.company_profile_id == self.company_profile.id)).all()
        )
        self.assertEqual(len(created), job.prospect_created_count)

        cancelled_log_entries = [e for e in job.log if e.get("event") == "job_cancelled"]
        self.assertGreaterEqual(len(cancelled_log_entries), 1)

    def test_cancellation_before_any_provider_starts_yields_cancelled_not_failed(self):
        self.search.query_spec = {"rows": [{"name": "Acme", "country": "United States"}]}
        self.db.commit()

        with patch("app.discovery.pipeline._is_cancellation_requested", return_value=True):
            job = run_discovery_search(self.db, self.search, self.user)

        self.assertEqual(job.status, DiscoveryJobStatus.CANCELLED)
        self.assertEqual(job.prospect_created_count, 0)
        self.assertEqual(job.providers_used, [])


if __name__ == "__main__":
    unittest.main()
