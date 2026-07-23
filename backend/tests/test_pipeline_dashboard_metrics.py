"""
Track C4 (dashboard-capabilities-architecture-plan.md, Sections 2-4):
Sales Pipeline, Pipeline Overview, and Revenue Pipeline all read the same
two Track C3 endpoints (GET .../opportunities/funnel and
GET .../opportunities/pipeline-value) - no new persistence, Opportunity/
OpportunityStageHistory remain the only source of truth (per the CEO's
explicit instruction for this track). This file covers the metrics math
both endpoints were revised to compute for C4: funnel conversion-rate
percentages, and the per-currency pipeline-value breakdown that resolves
the architecture doc's own explicitly-deferred Section 4.10 currency-
mixing decision.

Same conventions as test_opportunities_e2e.py: direct route-function
calls against a real SessionLocal, explicit child-then-parent teardown.
Requires a real database connection - not runnable in a sandbox with no
Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_pipeline_dashboard_metrics
"""
import unittest
import uuid
from datetime import datetime, timezone

# Must be imported before any ORM operation - see
# test_conversation_models.py's own docstring for the full explanation
# (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal

from app.api.routes.opportunities import (
    advance_opportunity_stage,
    create_opportunity_route,
    get_opportunity_funnel,
    get_opportunity_pipeline_value,
    update_opportunity,
)
from app.models.company_profile import CompanyProfile
from app.models.enums import OpportunityStage, UserRole
from app.models.opportunity import Opportunity
from app.models.opportunity_stage_history import OpportunityStageHistory
from app.models.prospect import Prospect
from app.models.user import User
from app.schemas.opportunity import AdvanceStageRequest, OpportunityCreate, OpportunityUpdate


class PipelineMetricsTestBase(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        now = datetime.now(timezone.utc)

        self.user_a = User(email=f"c4-a-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.user_b = User(email=f"c4-b-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add_all([self.user_a, self.user_b])
        self.db.flush()

        self.profile_a = CompanyProfile(owner_user_id=self.user_a.id, name="C4 Test Co A")
        self.profile_b = CompanyProfile(owner_user_id=self.user_b.id, name="C4 Test Co B")
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

    def tearDown(self):
        for opp_id in self._opportunity_ids:
            self.db.query(OpportunityStageHistory).filter(OpportunityStageHistory.opportunity_id == opp_id).delete()
            self.db.query(Opportunity).filter(Opportunity.id == opp_id).delete()
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

    def _create(self, profile, prospect, **overrides) -> Opportunity:
        payload = {"name": "Acme Corp - Q3 order", "prospect_id": prospect.id}
        payload.update(overrides)
        opportunity = create_opportunity_route(OpportunityCreate(**payload), profile=profile, db=self.db)
        self._opportunity_ids.append(opportunity.id)
        return opportunity

    def _advance(self, opportunity, to_stage, **kwargs):
        return advance_opportunity_stage(
            opportunity.id,
            AdvanceStageRequest(to_stage=to_stage, **kwargs),
            profile=self.profile_a if opportunity.company_profile_id == self.profile_a.id else self.profile_b,
            current_user=self.user_a if opportunity.company_profile_id == self.profile_a.id else self.user_b,
            db=self.db,
        )


class TestFunnelPipelineMetrics(PipelineMetricsTestBase):
    def test_every_declared_stage_present_even_at_zero(self):
        self._create(self.profile_a, self.prospect_a)
        funnel = get_opportunity_funnel(profile=self.profile_a, db=self.db)
        self.assertEqual(len(funnel), len(OpportunityStage))
        by_stage = {row["stage"]: row for row in funnel}
        self.assertEqual(by_stage[OpportunityStage.CLOSED_WON.value]["count"], 0)

    def test_conversion_rate_is_none_for_the_first_stage(self):
        self._create(self.profile_a, self.prospect_a)
        funnel = get_opportunity_funnel(profile=self.profile_a, db=self.db)
        by_stage = {row["stage"]: row for row in funnel}
        self.assertIsNone(by_stage[OpportunityStage.QUALIFIED_LEAD.value]["conversion_rate_from_previous"])

    def test_conversion_rate_is_none_when_previous_stage_has_zero_count(self):
        # No opportunity ever sits at MEETING, so SAMPLE's "conversion from
        # previous" has nothing meaningful to divide by.
        self._create(self.profile_a, self.prospect_a)
        funnel = get_opportunity_funnel(profile=self.profile_a, db=self.db)
        by_stage = {row["stage"]: row for row in funnel}
        self.assertIsNone(by_stage[OpportunityStage.SAMPLE.value]["conversion_rate_from_previous"])

    def test_conversion_rate_computed_correctly_between_populated_stages(self):
        # 4 created at QUALIFIED_LEAD, 2 advanced to MEETING - this is a
        # CURRENT-distribution ratio (see compute_funnel's own docstring
        # on why, given stages may be skipped), so after the move,
        # QUALIFIED_LEAD's current count is 2 (the two left behind) and
        # MEETING's current count is 2 (the two that moved) - a 100.0%
        # ratio of MEETING's count to QUALIFIED_LEAD's CURRENT count, not
        # "100% of everything that ever existed converted."
        opp1 = self._create(self.profile_a, self.prospect_a)
        opp2 = self._create(self.profile_a, self.prospect_a)
        self._create(self.profile_a, self.prospect_a)
        self._create(self.profile_a, self.prospect_a)
        self._advance(opp1, OpportunityStage.MEETING)
        self._advance(opp2, OpportunityStage.MEETING)

        funnel = get_opportunity_funnel(profile=self.profile_a, db=self.db)
        by_stage = {row["stage"]: row for row in funnel}
        self.assertEqual(by_stage[OpportunityStage.QUALIFIED_LEAD.value]["count"], 2)
        self.assertEqual(by_stage[OpportunityStage.MEETING.value]["count"], 2)
        self.assertEqual(by_stage[OpportunityStage.MEETING.value]["conversion_rate_from_previous"], 100.0)

    def test_closed_lost_conversion_rate_is_always_none(self):
        # CLOSED_LOST is a drop-off outcome, not a sequential funnel step -
        # it must never carry a "conversion from previous" percentage,
        # regardless of how many deals are lost.
        opp1 = self._create(self.profile_a, self.prospect_a)
        self._advance(opp1, OpportunityStage.CLOSED_LOST, lost_reason="Went with a competitor")
        funnel = get_opportunity_funnel(profile=self.profile_a, db=self.db)
        by_stage = {row["stage"]: row for row in funnel}
        self.assertIsNone(by_stage[OpportunityStage.CLOSED_LOST.value]["conversion_rate_from_previous"])
        self.assertEqual(by_stage[OpportunityStage.CLOSED_LOST.value]["count"], 1)

    def test_funnel_isolated_per_business(self):
        self._create(self.profile_a, self.prospect_a)
        self._create(self.profile_b, self.prospect_b)
        self._create(self.profile_b, self.prospect_b)
        funnel_a = get_opportunity_funnel(profile=self.profile_a, db=self.db)
        funnel_b = get_opportunity_funnel(profile=self.profile_b, db=self.db)
        by_stage_a = {row["stage"]: row["count"] for row in funnel_a}
        by_stage_b = {row["stage"]: row["count"] for row in funnel_b}
        self.assertEqual(by_stage_a[OpportunityStage.QUALIFIED_LEAD.value], 1)
        self.assertEqual(by_stage_b[OpportunityStage.QUALIFIED_LEAD.value], 2)

    def test_empty_pipeline_still_returns_every_stage_at_zero(self):
        # No opportunities at all for this business yet - the funnel must
        # still render every declared stage (all zero), not an empty list -
        # unlike pipeline-value below, which has no currency to key rows
        # off of and legitimately returns nothing.
        funnel = get_opportunity_funnel(profile=self.profile_b, db=self.db)
        self.assertEqual(len(funnel), len(OpportunityStage))
        self.assertTrue(all(row["count"] == 0 for row in funnel))
        self.assertTrue(all(row["conversion_rate_from_previous"] is None for row in funnel))


class TestPipelineValueRevenueCalculations(PipelineMetricsTestBase):
    def test_single_currency_returns_exactly_one_row(self):
        self._create(self.profile_a, self.prospect_a, estimated_revenue=1000.0, currency="USD")
        self._create(self.profile_a, self.prospect_a, estimated_revenue=500.0, currency="USD")
        result = get_opportunity_pipeline_value(profile=self.profile_a, db=self.db)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["currency"], "USD")
        self.assertEqual(result[0]["open_pipeline_value"], 1500.0)
        self.assertEqual(result[0]["closed_won_value"], 0.0)

    def test_open_vs_closed_won_are_kept_separate(self):
        opp1 = self._create(self.profile_a, self.prospect_a, estimated_revenue=1000.0, currency="USD")
        opp2 = self._create(self.profile_a, self.prospect_a, estimated_revenue=2000.0, currency="USD")
        self._advance(opp2, OpportunityStage.CLOSED_WON)
        update_opportunity(opp2.id, OpportunityUpdate(actual_revenue=1800.0), profile=self.profile_a, db=self.db)

        result = get_opportunity_pipeline_value(profile=self.profile_a, db=self.db)
        self.assertEqual(len(result), 1)
        row = result[0]
        # opp1 (still QUALIFIED_LEAD) contributes to open_pipeline_value;
        # opp2 is CLOSED_WON so it's excluded from open_pipeline_value and
        # its actual_revenue (not estimated_revenue) counts toward
        # closed_won_value instead.
        self.assertEqual(row["open_pipeline_value"], 1000.0)
        self.assertEqual(row["closed_won_value"], 1800.0)

    def test_closed_lost_contributes_to_neither_figure(self):
        opp1 = self._create(self.profile_a, self.prospect_a, estimated_revenue=1000.0, currency="USD")
        self._advance(opp1, OpportunityStage.CLOSED_LOST, lost_reason="Budget cut")
        result = get_opportunity_pipeline_value(profile=self.profile_a, db=self.db)
        # No open opportunities and no CLOSED_WON opportunities in USD -
        # the row should not exist at all (nothing to report), matching
        # this endpoint's own "no fabricated zero-value currency rows"
        # discipline.
        self.assertEqual(result, [])

    def test_mixed_currencies_return_one_row_per_currency_never_blended(self):
        # This is the exact scenario Section 4.10 of the architecture doc
        # flagged as a correctness risk: SUM(amount) across mixed
        # currencies is meaningless without conversion. Confirms the fix -
        # a per-currency breakdown, never one blind summed total.
        self._create(self.profile_a, self.prospect_a, estimated_revenue=1000.0, currency="USD")
        self._create(self.profile_a, self.prospect_a, estimated_revenue=2000.0, currency="EUR")
        result = get_opportunity_pipeline_value(profile=self.profile_a, db=self.db)
        by_currency = {row["currency"]: row["open_pipeline_value"] for row in result}
        self.assertEqual(len(result), 2)
        self.assertEqual(by_currency["USD"], 1000.0)
        self.assertEqual(by_currency["EUR"], 2000.0)
        # Never a blended 3000.0 total anywhere in the response.
        self.assertNotIn(3000.0, [row["open_pipeline_value"] for row in result])

    def test_opportunities_with_no_currency_set_get_their_own_none_bucket(self):
        self._create(self.profile_a, self.prospect_a, estimated_revenue=500.0)  # currency left unset
        result = get_opportunity_pipeline_value(profile=self.profile_a, db=self.db)
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["currency"])
        self.assertEqual(result[0]["open_pipeline_value"], 500.0)

    def test_empty_pipeline_returns_an_empty_list(self):
        # No opportunities at all for this business - an honest "nothing
        # to report" empty list, not a fabricated zero-value row.
        result = get_opportunity_pipeline_value(profile=self.profile_b, db=self.db)
        self.assertEqual(result, [])

    def test_pipeline_value_isolated_per_business(self):
        self._create(self.profile_a, self.prospect_a, estimated_revenue=1000.0, currency="USD")
        self._create(self.profile_b, self.prospect_b, estimated_revenue=9999.0, currency="USD")
        result_a = get_opportunity_pipeline_value(profile=self.profile_a, db=self.db)
        result_b = get_opportunity_pipeline_value(profile=self.profile_b, db=self.db)
        self.assertEqual(result_a[0]["open_pipeline_value"], 1000.0)
        self.assertEqual(result_b[0]["open_pipeline_value"], 9999.0)

    def test_opportunities_with_no_estimated_revenue_contribute_zero_not_none(self):
        self._create(self.profile_a, self.prospect_a, currency="USD")  # estimated_revenue left unset
        result = get_opportunity_pipeline_value(profile=self.profile_a, db=self.db)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["open_pipeline_value"], 0.0)


if __name__ == "__main__":
    unittest.main()
