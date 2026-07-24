"""
tests.test_discovery_search_service_e2e - M2 Phase 2.

DB-backed - requires a real database connection, not runnable in a
sandbox with no Docker/Postgres access (same disclosed limitation as
tests/test_discovery_job_cancellation.py and every other *_e2e.py test
in this project - see this project's own standing disclosure). Proves,
against the REAL app.discovery.pipeline.run_discovery_search() (not a
stand-in), the two things tests/test_search_service_pure.py's fakes
cannot: (1) a query-driven provider genuinely flows through
Normalization -> Validation -> Dedup -> Scoring exactly like manual_csv
always has, and (2) a candidate found by brave_search that shares a
website with one manual_csv already found in the SAME job collapses
into ONE Prospect via the existing, unmodified
app.discovery.dedup.find_duplicate() tier - "duplicate results across
providers" is a property of app.discovery.pipeline's own dedup layer,
not of app.discovery.search_service (see that module's own
TestDuplicateResultsAcrossProviders test for why it's deliberately
scoped to one provider per call).

BraveSearchProvider's own httpx call is never reached in these tests -
app.discovery.pipeline.search_service_discover is patched at the module
level pipeline.py actually calls it from, returning a canned
ProviderSearchOutcome instead. This exercises the REAL wiring inside
pipeline.py (is_search_provider() branch, QueryPlan construction from a
real ICPCriteria/Product's ORM relationships via
_build_query_plan_input(), the real per-provider commit/checkpoint
loop) while keeping the test independent of network access or a real
Brave Search API key - the same "patch at the pipeline call site, prove
the wiring, not the third-party API" approach
tests/test_discovery_job_cancellation.py's own
TestPipelineGracefulCancellation class already established.

Run standalone with:
    python -m unittest tests.test_discovery_search_service_e2e
"""
import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import select

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.discovery.pipeline import run_discovery_search
from app.discovery.providers.base import ProviderError, ProviderSearchOutcome, RawProviderResult
from app.models.company_profile import CompanyProfile
from app.models.discovery_job import DiscoveryJob
from app.models.discovery_job_provider_run import DiscoveryJobProviderRun
from app.models.discovery_provider_result import DiscoveryProviderResult
from app.models.discovery_run import DiscoveryRun
from app.models.discovery_search import DiscoverySearch
from app.models.enums import DiscoveryJobStatus, ProductStatus, UserRole
from app.models.icp_criteria import ICPCriteria
from app.models.product import Product
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.prospect_source import ProspectSource
from app.models.prospect_timeline_event import ProspectTimelineEvent
from app.models.search_template import SearchTemplate
from app.models.user import User


class SearchServiceE2ETestBase(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        self.user = User(email=f"m2-p2-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M2 Phase 2 Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.flush()

        self.product = Product(company_profile_id=self.company_profile.id, name="Cotton Yarn", status=ProductStatus.ACTIVE)
        self.db.add(self.product)
        self.db.flush()

        self.search_template = SearchTemplate(
            company_profile_id=self.company_profile.id, name="Phase 2 template", query_spec={}, is_system_default=False
        )
        self.db.add(self.search_template)
        self.db.flush()

        self.icp = ICPCriteria(
            company_profile_id=self.company_profile.id, version=1, name="Phase 2 ICP",
            is_active=True, minimum_confidence_score=None,
        )
        self.db.add(self.icp)
        self.db.commit()

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

        self.db.query(Product).filter(Product.company_profile_id == self.company_profile.id).delete(synchronize_session=False)
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


class TestBraveSearchFlowsThroughTheFullPipeline(SearchServiceE2ETestBase):
    def test_brave_search_candidate_is_normalized_validated_and_scored(self):
        search = DiscoverySearch(
            company_profile_id=self.company_profile.id,
            search_template_id=self.search_template.id,
            icp_criteria_id=self.icp.id,
            name="Phase 2 brave-only search",
            query_spec={},
            provider_keys=["brave_search"],
        )
        self.db.add(search)
        self.db.commit()

        canned_outcome = ProviderSearchOutcome(
            results=[
                RawProviderResult(
                    name="Acme Textiles", raw_payload={"title": "Acme Textiles"},
                    website="acme.example.com", provider_confidence=0.45,
                )
            ],
            request_count=1, api_cost=None, token_usage=None,
        )
        with patch("app.discovery.pipeline.search_service_discover", return_value=canned_outcome):
            job = run_discovery_search(self.db, search, self.user)

        self.assertEqual(job.status, DiscoveryJobStatus.COMPLETED)
        self.assertEqual(job.providers_used, ["brave_search"])
        self.assertEqual(job.prospect_created_count, 1)

        prospect = self.db.scalars(
            select(Prospect).where(Prospect.company_profile_id == self.company_profile.id)
        ).one()
        self.assertEqual(prospect.website, "acme.example.com")
        # Scoring ran on this prospect exactly like on any manual_csv one -
        # total_score is populated, not left at its default None.
        self.assertIsNotNone(prospect.total_score)


class TestDuplicateResultsAcrossProviders(SearchServiceE2ETestBase):
    def test_same_website_from_manual_csv_and_brave_search_collapses_into_one_prospect(self):
        search = DiscoverySearch(
            company_profile_id=self.company_profile.id,
            search_template_id=self.search_template.id,
            icp_criteria_id=self.icp.id,
            name="Phase 2 cross-provider dedup search",
            query_spec={"rows": [{"name": "Acme Textiles Ltd", "website": "acme.example.com", "country": "United States"}]},
            provider_keys=["manual_csv", "brave_search"],
        )
        self.db.add(search)
        self.db.commit()

        canned_outcome = ProviderSearchOutcome(
            results=[
                RawProviderResult(
                    name="Acme Textiles", raw_payload={"title": "Acme Textiles"},
                    website="acme.example.com", provider_confidence=0.45,
                )
            ],
            request_count=1, api_cost=None, token_usage=None,
        )
        with patch("app.discovery.pipeline.search_service_discover", return_value=canned_outcome):
            job = run_discovery_search(self.db, search, self.user)

        self.assertEqual(job.status, DiscoveryJobStatus.COMPLETED)
        self.assertEqual(sorted(job.providers_used), ["brave_search", "manual_csv"])
        # Exactly ONE Prospect, not two - the second (brave_search) sighting
        # of the same website is a re-sighting (matched_count), not a
        # second creation.
        self.assertEqual(job.prospect_created_count, 1)
        self.assertEqual(job.prospect_matched_count, 1)

        prospects = list(
            self.db.scalars(select(Prospect).where(Prospect.company_profile_id == self.company_profile.id)).all()
        )
        self.assertEqual(len(prospects), 1)

        # Both provider sightings are preserved as separate ProspectSource
        # rows - full audit trail is not lost by the dedup collapse.
        sources = list(
            self.db.scalars(select(ProspectSource).where(ProspectSource.prospect_id == prospects[0].id)).all()
        )
        self.assertEqual({s.provider_key for s in sources}, {"manual_csv", "brave_search"})


class TestUnconfiguredBraveSearchDegradesGracefully(SearchServiceE2ETestBase):
    def test_job_completes_with_manual_csv_only_when_brave_search_is_unconfigured(self):
        """No mocking here at all - BraveSearchProvider.health() genuinely
        returns False with no BRAVE_SEARCH_API_KEY set (this test's own
        environment), so this exercises the REAL
        app.discovery.search_service.SearchService.discover()'s own
        health() gate, raising ProviderError, which
        app.discovery.pipeline's existing per-provider try/except already
        handles exactly like any other provider failure - graceful
        degradation at the job level, unchanged by this phase."""
        search = DiscoverySearch(
            company_profile_id=self.company_profile.id,
            search_template_id=self.search_template.id,
            icp_criteria_id=self.icp.id,
            name="Phase 2 unconfigured brave_search search",
            query_spec={"rows": [{"name": "Acme Textiles Ltd", "website": "acme.example.com", "country": "United States"}]},
            provider_keys=["manual_csv", "brave_search"],
        )
        self.db.add(search)
        self.db.commit()

        job = run_discovery_search(self.db, search, self.user)

        self.assertEqual(job.status, DiscoveryJobStatus.PARTIALLY_COMPLETED)
        self.assertEqual(job.providers_used, ["manual_csv"])
        self.assertEqual(job.prospect_created_count, 1)
        self.assertIsNotNone(job.error_message)
        self.assertIn("brave_search", job.error_message)

        provider_runs = list(
            self.db.scalars(
                select(DiscoveryJobProviderRun).where(DiscoveryJobProviderRun.discovery_job_id == job.id)
            ).all()
        )
        failed_runs = [r for r in provider_runs if r.provider_key == "brave_search"]
        self.assertEqual(len(failed_runs), 1)
        self.assertEqual(failed_runs[0].status, "failed")


if __name__ == "__main__":
    unittest.main()
