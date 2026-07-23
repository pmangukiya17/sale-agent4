"""
Track C3 (dashboard-capabilities-architecture-plan.md, Section 1): the
Opportunity domain's real-DB coverage - CRUD, stage transitions
(including skipping stages), tenant isolation, stage-history tracking,
and edge cases. Same conventions as test_open_conversations_count.py /
test_ai_recommendations_portfolio.py: direct route-function calls
against a real SessionLocal, explicit child-then-parent teardown, no
pytest fixtures/rollback-based isolation. Requires a real database
connection - not runnable in a sandbox with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_opportunities_e2e
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

from app.api.routes.opportunities import (
    advance_opportunity_stage,
    create_opportunity_route,
    delete_opportunity,
    get_opportunity,
    get_opportunity_funnel,
    get_opportunity_pipeline_value,
    list_opportunities,
    update_opportunity,
)
from app.models.company_profile import CompanyProfile
from app.models.enums import OpportunityStage, UserRole
from app.models.opportunity import Opportunity
from app.models.opportunity_stage_history import OpportunityStageHistory
from app.models.prospect import Prospect
from app.models.user import User
from app.schemas.opportunity import AdvanceStageRequest, OpportunityCreate, OpportunityUpdate


class OpportunityTestBase(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        now = datetime.now(timezone.utc)

        self.user_a = User(email=f"c3-a-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.user_b = User(email=f"c3-b-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add_all([self.user_a, self.user_b])
        self.db.flush()

        self.profile_a = CompanyProfile(owner_user_id=self.user_a.id, name="C3 Test Co A")
        self.profile_b = CompanyProfile(owner_user_id=self.user_b.id, name="C3 Test Co B")
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
        payload = {
            "name": "Acme Corp - Q3 order",
            "prospect_id": prospect.id,
        }
        payload.update(overrides)
        opportunity = create_opportunity_route(OpportunityCreate(**payload), profile=profile, db=self.db)
        self._opportunity_ids.append(opportunity.id)
        return opportunity


class TestOpportunityCrud(OpportunityTestBase):
    def test_create_writes_opportunity_and_one_initial_history_row(self):
        opportunity = self._create(self.profile_a, self.prospect_a)
        self.assertEqual(opportunity.stage, OpportunityStage.QUALIFIED_LEAD)
        history = (
            self.db.query(OpportunityStageHistory)
            .filter(OpportunityStageHistory.opportunity_id == opportunity.id)
            .all()
        )
        self.assertEqual(len(history), 1)
        self.assertIsNone(history[0].from_stage)
        self.assertEqual(history[0].to_stage, OpportunityStage.QUALIFIED_LEAD)

    def test_create_rejects_a_prospect_from_another_business(self):
        with self.assertRaises(HTTPException) as ctx:
            create_opportunity_route(
                OpportunityCreate(name="Cross-tenant attempt", prospect_id=self.prospect_b.id),
                profile=self.profile_a,
                db=self.db,
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_get_returns_404_for_another_businesss_opportunity(self):
        opportunity = self._create(self.profile_a, self.prospect_a)
        with self.assertRaises(HTTPException) as ctx:
            get_opportunity(opportunity.id, profile=self.profile_b, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_update_changes_fields_but_never_stage(self):
        opportunity = self._create(self.profile_a, self.prospect_a, estimated_revenue=1000.0)
        updated = update_opportunity(
            opportunity.id,
            OpportunityUpdate(estimated_revenue=5000.0, currency="USD"),
            profile=self.profile_a,
            db=self.db,
        )
        self.assertEqual(float(updated.estimated_revenue), 5000.0)
        self.assertEqual(updated.currency, "USD")
        self.assertEqual(updated.stage, OpportunityStage.QUALIFIED_LEAD)
        # OpportunityUpdate's schema has no `stage` field at all - a PATCH
        # request body literally cannot carry one; confirmed structurally,
        # not just by this one assertion.
        self.assertNotIn("stage", OpportunityUpdate.model_fields)

    def test_list_is_isolated_per_business(self):
        self._create(self.profile_a, self.prospect_a)
        self._create(self.profile_a, self.prospect_a)
        self._create(self.profile_b, self.prospect_b)
        result_a = list_opportunities(stage=None, prospect_id=None, profile=self.profile_a, db=self.db)
        result_b = list_opportunities(stage=None, prospect_id=None, profile=self.profile_b, db=self.db)
        self.assertEqual(len(result_a), 2)
        self.assertEqual(len(result_b), 1)

    def test_list_filters_by_stage(self):
        opp1 = self._create(self.profile_a, self.prospect_a)
        self._create(self.profile_a, self.prospect_a)
        advance_opportunity_stage(
            opp1.id,
            AdvanceStageRequest(to_stage=OpportunityStage.NEGOTIATION),
            profile=self.profile_a,
            current_user=self.user_a,
            db=self.db,
        )
        result = list_opportunities(
            stage=OpportunityStage.NEGOTIATION, prospect_id=None, profile=self.profile_a, db=self.db
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, opp1.id)


class TestOpportunityStageTransitions(OpportunityTestBase):
    def test_skipping_stages_is_allowed_and_recorded(self):
        opportunity = self._create(self.profile_a, self.prospect_a)
        updated = advance_opportunity_stage(
            opportunity.id,
            AdvanceStageRequest(to_stage=OpportunityStage.PURCHASE_ORDER),
            profile=self.profile_a,
            current_user=self.user_a,
            db=self.db,
        )
        self.assertEqual(updated.stage, OpportunityStage.PURCHASE_ORDER)
        history = (
            self.db.query(OpportunityStageHistory)
            .filter(OpportunityStageHistory.opportunity_id == opportunity.id)
            .order_by(OpportunityStageHistory.changed_at)
            .all()
        )
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1].from_stage, OpportunityStage.QUALIFIED_LEAD)
        self.assertEqual(history[1].to_stage, OpportunityStage.PURCHASE_ORDER)

    def test_same_stage_transition_returns_400(self):
        opportunity = self._create(self.profile_a, self.prospect_a)
        with self.assertRaises(HTTPException) as ctx:
            advance_opportunity_stage(
                opportunity.id,
                AdvanceStageRequest(to_stage=OpportunityStage.QUALIFIED_LEAD),
                profile=self.profile_a,
                current_user=self.user_a,
                db=self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_advance_stage_rejects_another_businesss_opportunity(self):
        opportunity = self._create(self.profile_a, self.prospect_a)
        with self.assertRaises(HTTPException) as ctx:
            advance_opportunity_stage(
                opportunity.id,
                AdvanceStageRequest(to_stage=OpportunityStage.MEETING),
                profile=self.profile_b,
                current_user=self.user_b,
                db=self.db,
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_closing_won_sets_closed_at(self):
        opportunity = self._create(self.profile_a, self.prospect_a)
        updated = advance_opportunity_stage(
            opportunity.id,
            AdvanceStageRequest(to_stage=OpportunityStage.CLOSED_WON),
            profile=self.profile_a,
            current_user=self.user_a,
            db=self.db,
        )
        self.assertIsNotNone(updated.closed_at)

    def test_closing_lost_sets_closed_at_and_lost_reason(self):
        opportunity = self._create(self.profile_a, self.prospect_a)
        updated = advance_opportunity_stage(
            opportunity.id,
            AdvanceStageRequest(to_stage=OpportunityStage.CLOSED_LOST, lost_reason="Chose a competitor"),
            profile=self.profile_a,
            current_user=self.user_a,
            db=self.db,
        )
        self.assertIsNotNone(updated.closed_at)
        self.assertEqual(updated.lost_reason, "Chose a competitor")

    def test_reopening_a_closed_deal_clears_closed_at_and_lost_reason(self):
        opportunity = self._create(self.profile_a, self.prospect_a)
        advance_opportunity_stage(
            opportunity.id,
            AdvanceStageRequest(to_stage=OpportunityStage.CLOSED_LOST, lost_reason="Budget cut"),
            profile=self.profile_a,
            current_user=self.user_a,
            db=self.db,
        )
        reopened = advance_opportunity_stage(
            opportunity.id,
            AdvanceStageRequest(to_stage=OpportunityStage.NEGOTIATION),
            profile=self.profile_a,
            current_user=self.user_a,
            db=self.db,
        )
        self.assertIsNone(reopened.closed_at)
        self.assertIsNone(reopened.lost_reason)

    def test_full_history_reflects_every_recorded_transition_in_order(self):
        opportunity = self._create(self.profile_a, self.prospect_a)
        for stage in (OpportunityStage.MEETING, OpportunityStage.NEGOTIATION, OpportunityStage.CLOSED_WON):
            advance_opportunity_stage(
                opportunity.id,
                AdvanceStageRequest(to_stage=stage),
                profile=self.profile_a,
                current_user=self.user_a,
                db=self.db,
            )
        history = (
            self.db.query(OpportunityStageHistory)
            .filter(OpportunityStageHistory.opportunity_id == opportunity.id)
            .order_by(OpportunityStageHistory.changed_at)
            .all()
        )
        recorded_path = [(h.from_stage, h.to_stage) for h in history]
        self.assertEqual(
            recorded_path,
            [
                (None, OpportunityStage.QUALIFIED_LEAD),
                (OpportunityStage.QUALIFIED_LEAD, OpportunityStage.MEETING),
                (OpportunityStage.MEETING, OpportunityStage.NEGOTIATION),
                (OpportunityStage.NEGOTIATION, OpportunityStage.CLOSED_WON),
            ],
        )


class TestOpportunityFunnelAndPipelineValue(OpportunityTestBase):
    def test_funnel_counts_every_declared_stage_including_zero(self):
        opp1 = self._create(self.profile_a, self.prospect_a)
        self._create(self.profile_a, self.prospect_a)
        advance_opportunity_stage(
            opp1.id,
            AdvanceStageRequest(to_stage=OpportunityStage.NEGOTIATION),
            profile=self.profile_a,
            current_user=self.user_a,
            db=self.db,
        )
        funnel = get_opportunity_funnel(profile=self.profile_a, db=self.db)
        by_stage = {row["stage"]: row["count"] for row in funnel}
        self.assertEqual(len(funnel), len(OpportunityStage))  # every declared stage present
        self.assertEqual(by_stage[OpportunityStage.QUALIFIED_LEAD.value], 1)
        self.assertEqual(by_stage[OpportunityStage.NEGOTIATION.value], 1)
        self.assertEqual(by_stage[OpportunityStage.CLOSED_WON.value], 0)

    def test_funnel_is_isolated_per_business(self):
        self._create(self.profile_a, self.prospect_a)
        self._create(self.profile_b, self.prospect_b)
        self._create(self.profile_b, self.prospect_b)
        funnel_a = get_opportunity_funnel(profile=self.profile_a, db=self.db)
        funnel_b = get_opportunity_funnel(profile=self.profile_b, db=self.db)
        by_stage_a = {row["stage"]: row["count"] for row in funnel_a}
        by_stage_b = {row["stage"]: row["count"] for row in funnel_b}
        self.assertEqual(by_stage_a[OpportunityStage.QUALIFIED_LEAD.value], 1)
        self.assertEqual(by_stage_b[OpportunityStage.QUALIFIED_LEAD.value], 2)

    def test_pipeline_value_sums_open_estimated_revenue_and_separately_closed_won_actual_revenue(self):
        opp1 = self._create(self.profile_a, self.prospect_a, estimated_revenue=1000.0)
        opp2 = self._create(self.profile_a, self.prospect_a, estimated_revenue=2000.0)
        advance_opportunity_stage(
            opp2.id,
            AdvanceStageRequest(to_stage=OpportunityStage.CLOSED_WON),
            profile=self.profile_a,
            current_user=self.user_a,
            db=self.db,
        )
        update_opportunity(opp2.id, OpportunityUpdate(actual_revenue=1800.0), profile=self.profile_a, db=self.db)

        result = get_opportunity_pipeline_value(profile=self.profile_a, db=self.db)
        # opp1 is still open (QUALIFIED_LEAD) - its estimated_revenue counts
        # toward open_pipeline_value; opp2 is CLOSED_WON, so its
        # estimated_revenue is excluded from open_pipeline_value and its
        # actual_revenue counts toward closed_won_value instead.
        self.assertEqual(result["open_pipeline_value"], 1000.0)
        self.assertEqual(result["closed_won_value"], 1800.0)

    def test_pipeline_value_is_zero_for_a_business_with_no_opportunities(self):
        result = get_opportunity_pipeline_value(profile=self.profile_b, db=self.db)
        self.assertEqual(result["open_pipeline_value"], 0.0)
        self.assertEqual(result["closed_won_value"], 0.0)


class TestOpportunityDelete(OpportunityTestBase):
    def test_hard_delete_succeeds_before_any_stage_advance(self):
        opportunity = self._create(self.profile_a, self.prospect_a)
        delete_opportunity(opportunity.id, profile=self.profile_a, db=self.db)
        self._opportunity_ids.remove(opportunity.id)  # already gone - nothing left for tearDown to clean up
        self.assertIsNone(self.db.get(Opportunity, opportunity.id))

    def test_hard_delete_is_refused_once_a_real_stage_transition_is_recorded(self):
        opportunity = self._create(self.profile_a, self.prospect_a)
        advance_opportunity_stage(
            opportunity.id,
            AdvanceStageRequest(to_stage=OpportunityStage.MEETING),
            profile=self.profile_a,
            current_user=self.user_a,
            db=self.db,
        )
        with self.assertRaises(HTTPException) as ctx:
            delete_opportunity(opportunity.id, profile=self.profile_a, db=self.db)
        self.assertEqual(ctx.exception.status_code, 400)
        # Still there afterward - the refusal must not have partially
        # deleted anything.
        self.assertIsNotNone(self.db.get(Opportunity, opportunity.id))

    def test_delete_rejects_another_businesss_opportunity(self):
        opportunity = self._create(self.profile_a, self.prospect_a)
        with self.assertRaises(HTTPException) as ctx:
            delete_opportunity(opportunity.id, profile=self.profile_b, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
