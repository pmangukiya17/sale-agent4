"""
Track C5 (dashboard-capabilities-architecture-plan.md, Section 6): the
Mailbox Brief's real-DB coverage - generation, persistence, retrieval,
regeneration, tenant isolation, empty-workspace behavior, and edge
cases. Same conventions as test_opportunities_e2e.py /
test_pipeline_dashboard_metrics.py: direct route-function calls against
a real SessionLocal, explicit child-then-parent teardown. Requires a
real database connection - not runnable in a sandbox with no
Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_mailbox_brief_e2e
"""
import unittest
import uuid
from datetime import datetime, timezone

# Must be imported before any ORM operation - see
# test_conversation_models.py's own docstring for the full explanation
# (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from fastapi import HTTPException

from app.api.routes.mailbox_brief import generate_mailbox_brief, get_mailbox_brief
from app.api.routes.opportunities import advance_opportunity_stage, create_opportunity_route
from app.mailbox_brief.engine.deterministic_stub import AI_MODEL, AI_PROVIDER
from app.models.company_profile import CompanyProfile
from app.models.conversation import Conversation
from app.models.enums import (
    OpportunityStage,
    ProviderConnectionStatus,
    RecommendationStatus,
    RecommendationType,
    UserRole,
)
from app.models.mailbox_brief import MailboxBrief
from app.models.opportunity import Opportunity
from app.models.opportunity_stage_history import OpportunityStageHistory
from app.models.prospect import Prospect
from app.models.provider_connection import ProviderConnection
from app.models.recommendation import Recommendation
from app.models.user import User
from app.schemas.opportunity import AdvanceStageRequest, OpportunityCreate


class MailboxBriefTestBase(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        now = datetime.now(timezone.utc)

        self.user_a = User(email=f"c5-a-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.user_b = User(email=f"c5-b-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add_all([self.user_a, self.user_b])
        self.db.flush()

        self.profile_a = CompanyProfile(owner_user_id=self.user_a.id, name="C5 Test Co A")
        self.profile_b = CompanyProfile(owner_user_id=self.user_b.id, name="C5 Test Co B")
        self.db.add_all([self.profile_a, self.profile_b])
        self.db.flush()

        self.prospect_a = Prospect(
            company_profile_id=self.profile_a.id, name="A Prospect", first_discovered_at=now, last_seen_at=now
        )
        self.prospect_b = Prospect(
            company_profile_id=self.profile_b.id, name="B Prospect", first_discovered_at=now, last_seen_at=now
        )
        self.db.add_all([self.prospect_a, self.prospect_b])
        self.db.commit()

        self._opportunity_ids: list[uuid.UUID] = []
        self._recommendation_ids: list[uuid.UUID] = []
        self._conversation_ids: list[uuid.UUID] = []
        self._connection_ids: list[uuid.UUID] = []
        self._brief_ids: list[uuid.UUID] = []

    def tearDown(self):
        self.db.query(MailboxBrief).filter(MailboxBrief.id.in_(self._brief_ids)).delete(synchronize_session=False)
        self.db.query(Conversation).filter(Conversation.id.in_(self._conversation_ids)).delete(
            synchronize_session=False
        )
        self.db.query(ProviderConnection).filter(ProviderConnection.id.in_(self._connection_ids)).delete(
            synchronize_session=False
        )
        self.db.query(Recommendation).filter(Recommendation.id.in_(self._recommendation_ids)).delete(
            synchronize_session=False
        )
        for opp_id in self._opportunity_ids:
            self.db.query(OpportunityStageHistory).filter(OpportunityStageHistory.opportunity_id == opp_id).delete()
        self.db.query(Opportunity).filter(Opportunity.id.in_(self._opportunity_ids)).delete(
            synchronize_session=False
        )
        self.db.commit()
        self.db.query(Prospect).filter(Prospect.id.in_([self.prospect_a.id, self.prospect_b.id])).delete(
            synchronize_session=False
        )
        self.db.query(CompanyProfile).filter(CompanyProfile.id.in_([self.profile_a.id, self.profile_b.id])).delete(
            synchronize_session=False
        )
        self.db.query(User).filter(User.id.in_([self.user_a.id, self.user_b.id])).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def _make_opportunity(self, profile, prospect, **overrides):
        payload = {"name": "Acme Corp - Q3 order", "prospect_id": prospect.id}
        payload.update(overrides)
        opportunity = create_opportunity_route(OpportunityCreate(**payload), profile=profile, db=self.db)
        self._opportunity_ids.append(opportunity.id)
        return opportunity

    def _make_recommendation(self, prospect, **overrides):
        defaults = dict(
            prospect_id=prospect.id,
            recommendation_type=RecommendationType.PRODUCT_FIT,
            title="Recommend the bulk cotton line",
            status=RecommendationStatus.NEW,
            confidence=0.8,
        )
        defaults.update(overrides)
        rec = Recommendation(**defaults)
        self.db.add(rec)
        self.db.commit()
        self._recommendation_ids.append(rec.id)
        return rec

    def _make_conversation(self, profile, **overrides):
        connection = ProviderConnection(
            company_profile_id=profile.id, provider_key="outlook", status=ProviderConnectionStatus.CONNECTED
        )
        self.db.add(connection)
        self.db.commit()
        self._connection_ids.append(connection.id)

        defaults = dict(company_profile_id=profile.id, provider_connection_id=connection.id)
        defaults.update(overrides)
        conversation = Conversation(**defaults)
        self.db.add(conversation)
        self.db.commit()
        self._conversation_ids.append(conversation.id)
        return conversation


class TestMailboxBriefGeneration(MailboxBriefTestBase):
    def test_generate_persists_a_brief_with_real_derived_data(self):
        self._make_conversation(self.profile_a, needs_human_review=True)
        self._make_recommendation(self.prospect_a)
        self._make_opportunity(self.profile_a, self.prospect_a, estimated_revenue=1000.0, currency="USD")

        brief = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(brief.id)

        self.assertEqual(brief.company_profile_id, self.profile_a.id)
        self.assertEqual(brief.ai_provider, AI_PROVIDER)
        self.assertEqual(brief.ai_model, AI_MODEL)
        self.assertTrue(len(brief.summary) > 0)
        self.assertEqual(brief.requested_by_user_id, self.user_a.id)
        self.assertIsNotNone(brief.generated_at)
        self.assertEqual(brief.statistics["conversations_needing_review"], 1)
        self.assertEqual(brief.statistics["open_opportunity_count"], 1)
        self.assertEqual(len(brief.recommendations), 2)  # one "review conversations" + one AI recommendation

    def test_generate_writes_exactly_one_new_row_per_call(self):
        before_count = self.db.query(MailboxBrief).filter(MailboxBrief.company_profile_id == self.profile_a.id).count()
        brief = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(brief.id)
        after_count = self.db.query(MailboxBrief).filter(MailboxBrief.company_profile_id == self.profile_a.id).count()
        self.assertEqual(after_count, before_count + 1)


class TestMailboxBriefRetrieval(MailboxBriefTestBase):
    def test_get_returns_404_when_nothing_generated_yet(self):
        with self.assertRaises(HTTPException) as ctx:
            get_mailbox_brief(profile=self.profile_a, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_get_never_creates_a_brief_as_a_side_effect(self):
        before_count = self.db.query(MailboxBrief).filter(MailboxBrief.company_profile_id == self.profile_a.id).count()
        with self.assertRaises(HTTPException):
            get_mailbox_brief(profile=self.profile_a, db=self.db)
        with self.assertRaises(HTTPException):
            get_mailbox_brief(profile=self.profile_a, db=self.db)
        after_count = self.db.query(MailboxBrief).filter(MailboxBrief.company_profile_id == self.profile_a.id).count()
        self.assertEqual(after_count, before_count)

    def test_get_returns_the_generated_brief(self):
        generated = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(generated.id)
        fetched = get_mailbox_brief(profile=self.profile_a, db=self.db)
        self.assertEqual(fetched.id, generated.id)


class TestMailboxBriefRegeneration(MailboxBriefTestBase):
    def test_regeneration_creates_a_new_row_rather_than_overwriting(self):
        first = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(first.id)
        second = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(second.id)

        self.assertNotEqual(first.id, second.id)
        total = self.db.query(MailboxBrief).filter(MailboxBrief.company_profile_id == self.profile_a.id).count()
        self.assertEqual(total, 2)

    def test_get_returns_the_most_recently_generated_brief(self):
        first = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(first.id)
        second = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(second.id)

        fetched = get_mailbox_brief(profile=self.profile_a, db=self.db)
        self.assertEqual(fetched.id, second.id)

    def test_earlier_briefs_stay_a_frozen_snapshot_after_workspace_data_changes(self):
        first = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(first.id)
        self.assertEqual(first.statistics["open_opportunity_count"], 0)

        # Workspace changes after the first brief was generated.
        self._make_opportunity(self.profile_a, self.prospect_a, estimated_revenue=500.0, currency="USD")

        second = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(second.id)

        # The first brief's own persisted statistics must not have
        # silently changed - it's a snapshot, not a live view.
        self.db.refresh(first)
        self.assertEqual(first.statistics["open_opportunity_count"], 0)
        self.assertEqual(second.statistics["open_opportunity_count"], 1)


class TestMailboxBriefTenantIsolation(MailboxBriefTestBase):
    def test_a_businesss_brief_is_invisible_to_another_business(self):
        brief_a = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(brief_a.id)

        with self.assertRaises(HTTPException) as ctx:
            get_mailbox_brief(profile=self.profile_b, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_each_business_generates_its_own_independent_brief(self):
        self._make_opportunity(self.profile_a, self.prospect_a, estimated_revenue=1000.0, currency="USD")
        self._make_opportunity(self.profile_b, self.prospect_b, estimated_revenue=9999.0, currency="EUR")

        brief_a = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(brief_a.id)
        brief_b = generate_mailbox_brief(profile=self.profile_b, current_user=self.user_b, db=self.db)
        self._brief_ids.append(brief_b.id)

        self.assertNotEqual(brief_a.id, brief_b.id)
        self.assertEqual(brief_a.statistics["pipeline_value_breakdown"][0]["currency"], "USD")
        self.assertEqual(brief_b.statistics["pipeline_value_breakdown"][0]["currency"], "EUR")


class TestMailboxBriefEmptyWorkspaceAndEdgeCases(MailboxBriefTestBase):
    def test_empty_workspace_generates_an_honest_brief_not_an_error(self):
        brief = generate_mailbox_brief(profile=self.profile_b, current_user=self.user_b, db=self.db)
        self._brief_ids.append(brief.id)

        self.assertIn("No open conversations", brief.summary)
        self.assertIn("No opportunities have been created yet", brief.summary)
        self.assertEqual(brief.recommendations, [])
        self.assertEqual(brief.statistics["open_conversations_count"], 0)
        self.assertEqual(brief.statistics["open_opportunity_count"], 0)
        self.assertEqual(brief.statistics["pipeline_value_breakdown"], [])

    def test_recommendations_only_no_conversations_needing_review(self):
        self._make_recommendation(self.prospect_a)
        brief = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(brief.id)
        self.assertEqual(len(brief.recommendations), 1)
        self.assertEqual(brief.recommendations[0]["source_type"], "recommendation")

    def test_conversations_needing_review_only_no_recommendations(self):
        self._make_conversation(self.profile_a, needs_human_review=True)
        brief = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(brief.id)
        self.assertEqual(len(brief.recommendations), 1)
        self.assertEqual(brief.recommendations[0]["source_type"], "conversation")

    def test_dismissed_recommendations_are_excluded(self):
        self._make_recommendation(self.prospect_a, status=RecommendationStatus.DISMISSED)
        brief = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(brief.id)
        self.assertEqual(brief.statistics["recommendation_count"], 0)
        self.assertEqual(brief.recommendations, [])

    def test_closed_opportunities_are_reflected_in_statistics_not_open_count(self):
        opp = self._make_opportunity(self.profile_a, self.prospect_a, estimated_revenue=1000.0, currency="USD")
        advance_opportunity_stage(
            opp.id,
            AdvanceStageRequest(to_stage=OpportunityStage.CLOSED_WON),
            profile=self.profile_a,
            current_user=self.user_a,
            db=self.db,
        )
        brief = generate_mailbox_brief(profile=self.profile_a, current_user=self.user_a, db=self.db)
        self._brief_ids.append(brief.id)
        self.assertEqual(brief.statistics["open_opportunity_count"], 0)
        self.assertEqual(brief.statistics["closed_won_count"], 1)
        self.assertIn("1 won", brief.summary)


if __name__ == "__main__":
    unittest.main()
