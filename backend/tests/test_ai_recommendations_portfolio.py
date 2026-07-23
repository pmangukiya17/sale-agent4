"""
Track C2 (dashboard-capabilities-architecture-plan.md): the AI
Recommendations dashboard widget's own cross-portfolio endpoint,
GET /company-profiles/{id}/recommendations. Real-DB test, same
conventions as test_open_conversations_count.py (direct route-function
calls against a real SessionLocal, explicit child-then-parent teardown,
no pytest fixtures/rollback-based isolation - this codebase doesn't use
either pattern anywhere else). Requires a real database connection - not
runnable in a sandbox with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_ai_recommendations_portfolio
"""
import unittest
import uuid
from datetime import datetime, timezone

# Must be imported before any ORM operation - see
# test_conversation_models.py's own docstring for the full explanation
# (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.api.routes.recommendations import list_portfolio_recommendations
from app.models.company_profile import CompanyProfile
from app.models.enums import RecommendationStatus, RecommendationType, UserRole
from app.models.prospect import Prospect
from app.models.recommendation import Recommendation
from app.models.user import User


class TestAiRecommendationsPortfolio(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        now = datetime.now(timezone.utc)

        # Two entirely separate businesses/owners, so every assertion
        # below can prove tenant isolation, not just "the endpoint
        # works" - same pattern test_open_conversations_count.py already
        # established for Track C1.
        self.user_a = User(email=f"c2-a-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.user_b = User(email=f"c2-b-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add_all([self.user_a, self.user_b])
        self.db.flush()

        self.profile_a = CompanyProfile(owner_user_id=self.user_a.id, name="C2 Test Co A")
        self.profile_b = CompanyProfile(owner_user_id=self.user_b.id, name="C2 Test Co B")
        self.db.add_all([self.profile_a, self.profile_b])
        self.db.flush()

        self.prospect_a1 = Prospect(
            company_profile_id=self.profile_a.id, name="A Prospect 1", first_discovered_at=now, last_seen_at=now
        )
        self.prospect_a2 = Prospect(
            company_profile_id=self.profile_a.id, name="A Prospect 2", first_discovered_at=now, last_seen_at=now
        )
        self.prospect_b1 = Prospect(
            company_profile_id=self.profile_b.id, name="B Prospect 1", first_discovered_at=now, last_seen_at=now
        )
        self.db.add_all([self.prospect_a1, self.prospect_a2, self.prospect_b1])
        self.db.commit()

        # Business A: 2 NEW + 1 DISMISSED across two different prospects.
        # Business B: 4 NEW on its own prospect - a deliberately different,
        # larger count than A's, so a test that accidentally counted
        # across both businesses would be caught immediately by a wrong
        # number, not masked by a coincidence.
        self.recs_a = [
            Recommendation(
                prospect_id=self.prospect_a1.id,
                recommendation_type=RecommendationType.PRODUCT_FIT,
                title="A - product fit 1",
                status=RecommendationStatus.NEW,
            ),
            Recommendation(
                prospect_id=self.prospect_a2.id,
                recommendation_type=RecommendationType.SALES_ANGLE,
                title="A - sales angle",
                status=RecommendationStatus.NEW,
            ),
            Recommendation(
                prospect_id=self.prospect_a1.id,
                recommendation_type=RecommendationType.TALKING_POINT,
                title="A - dismissed talking point",
                status=RecommendationStatus.DISMISSED,
            ),
        ]
        self.recs_b = [
            Recommendation(
                prospect_id=self.prospect_b1.id,
                recommendation_type=RecommendationType.PRODUCT_FIT,
                title=f"B - product fit {i}",
                status=RecommendationStatus.NEW,
            )
            for i in range(4)
        ]
        self.db.add_all(self.recs_a + self.recs_b)
        self.db.commit()

    def tearDown(self):
        for rec in self.recs_a + self.recs_b:
            self.db.query(Recommendation).filter(Recommendation.id == rec.id).delete()
        self.db.commit()
        self.db.query(Prospect).filter(
            Prospect.id.in_([self.prospect_a1.id, self.prospect_a2.id, self.prospect_b1.id])
        ).delete(synchronize_session=False)
        self.db.query(CompanyProfile).filter(CompanyProfile.id.in_([self.profile_a.id, self.profile_b.id])).delete(
            synchronize_session=False
        )
        self.db.query(User).filter(User.id.in_([self.user_a.id, self.user_b.id])).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def test_returns_only_the_callers_own_portfolio(self):
        result = list_portfolio_recommendations(
            status_filter=None, recommendation_type=None, limit=20, profile=self.profile_a, db=self.db
        )
        self.assertEqual(len(result), 3)
        self.assertTrue(all(r.prospect.id in (self.prospect_a1.id, self.prospect_a2.id) for r in result))

    def test_counts_are_isolated_per_business(self):
        result = list_portfolio_recommendations(
            status_filter=None, recommendation_type=None, limit=20, profile=self.profile_b, db=self.db
        )
        self.assertEqual(len(result), 4)
        self.assertTrue(all(r.prospect.id == self.prospect_b1.id for r in result))

    def test_status_filter_excludes_dismissed(self):
        result = list_portfolio_recommendations(
            status_filter=RecommendationStatus.NEW, recommendation_type=None, limit=20, profile=self.profile_a, db=self.db
        )
        self.assertEqual(len(result), 2)
        self.assertTrue(all(r.status == RecommendationStatus.NEW for r in result))

    def test_limit_caps_the_result_set(self):
        result = list_portfolio_recommendations(
            status_filter=None, recommendation_type=None, limit=1, profile=self.profile_a, db=self.db
        )
        self.assertEqual(len(result), 1)

    def test_each_row_carries_which_prospect_it_belongs_to(self):
        result = list_portfolio_recommendations(
            status_filter=None, recommendation_type=None, limit=20, profile=self.profile_a, db=self.db
        )
        prospect_names = {r.prospect.name for r in result}
        self.assertTrue(prospect_names.issubset({"A Prospect 1", "A Prospect 2"}))

    def test_zero_recommendations_returns_empty_list_not_error(self):
        # A brand-new business with no prospects/recommendations at all yet.
        user_c = User(email=f"c2-c-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(user_c)
        self.db.flush()
        profile_c = CompanyProfile(owner_user_id=user_c.id, name="C2 Test Co C - Empty")
        self.db.add(profile_c)
        self.db.commit()
        try:
            result = list_portfolio_recommendations(
                status_filter=None, recommendation_type=None, limit=20, profile=profile_c, db=self.db
            )
            self.assertEqual(result, [])
        finally:
            self.db.query(CompanyProfile).filter(CompanyProfile.id == profile_c.id).delete()
            self.db.query(User).filter(User.id == user_c.id).delete()
            self.db.commit()


if __name__ == "__main__":
    unittest.main()
