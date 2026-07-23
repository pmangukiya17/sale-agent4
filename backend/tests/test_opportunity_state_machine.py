"""
Pure-logic tests for app/opportunities/state_machine.py - no DB, no
network, no fixtures. Mirrors test_crm_automation_state_machine.py's own
convention: state_machine.py is deliberately pure, so this exercises real,
executable code end to end without a Postgres connection.

Covers: stages MAY be skipped in either direction (the CEO's explicit
design decision for this track - no linear-order enforcement anywhere),
the only rejected transition is a same-stage no-op, and closed_at/
is_closed derivation for every stage.

Run standalone with:
    python -m unittest tests.test_opportunity_state_machine
"""
import unittest

from app.models.enums import OpportunityStage
from app.opportunities.state_machine import InvalidStageTransitionError, is_closed_stage, plan_stage_transition


class TestIsClosedStage(unittest.TestCase):
    def test_closed_won_and_closed_lost_are_closed(self):
        self.assertTrue(is_closed_stage(OpportunityStage.CLOSED_WON))
        self.assertTrue(is_closed_stage(OpportunityStage.CLOSED_LOST))

    def test_every_other_stage_is_not_closed(self):
        open_stages = (
            OpportunityStage.QUALIFIED_LEAD,
            OpportunityStage.MEETING,
            OpportunityStage.SAMPLE,
            OpportunityStage.QUOTATION,
            OpportunityStage.NEGOTIATION,
            OpportunityStage.PURCHASE_ORDER,
        )
        for stage in open_stages:
            with self.subTest(stage=stage):
                self.assertFalse(is_closed_stage(stage))


class TestPlanStageTransition(unittest.TestCase):
    def test_same_stage_transition_is_rejected(self):
        for stage in OpportunityStage:
            with self.subTest(stage=stage):
                with self.assertRaises(InvalidStageTransitionError):
                    plan_stage_transition(stage, stage)

    def test_skipping_stages_forward_is_allowed(self):
        # Per the CEO's explicit direction: no linear-order enforcement.
        # A deal may jump straight from QUALIFIED_LEAD to PURCHASE_ORDER,
        # skipping MEETING/SAMPLE/QUOTATION/NEGOTIATION entirely.
        transition = plan_stage_transition(OpportunityStage.QUALIFIED_LEAD, OpportunityStage.PURCHASE_ORDER)
        self.assertEqual(transition.to_stage, OpportunityStage.PURCHASE_ORDER)
        self.assertFalse(transition.is_closed)

    def test_moving_backwards_is_allowed(self):
        # Re-opening a stalled deal back to an earlier stage is not a
        # "workflow violation" in this design - no rule ever forbids it.
        transition = plan_stage_transition(OpportunityStage.NEGOTIATION, OpportunityStage.MEETING)
        self.assertEqual(transition.to_stage, OpportunityStage.MEETING)
        self.assertFalse(transition.is_closed)

    def test_every_stage_reachable_from_every_other_stage(self):
        for from_stage in OpportunityStage:
            for to_stage in OpportunityStage:
                if from_stage == to_stage:
                    continue
                with self.subTest(from_stage=from_stage, to_stage=to_stage):
                    transition = plan_stage_transition(from_stage, to_stage)
                    self.assertEqual(transition.to_stage, to_stage)

    def test_transitioning_into_closed_won_sets_is_closed(self):
        transition = plan_stage_transition(OpportunityStage.NEGOTIATION, OpportunityStage.CLOSED_WON)
        self.assertTrue(transition.is_closed)

    def test_transitioning_into_closed_lost_sets_is_closed(self):
        transition = plan_stage_transition(OpportunityStage.QUALIFIED_LEAD, OpportunityStage.CLOSED_LOST)
        self.assertTrue(transition.is_closed)

    def test_reopening_from_a_closed_stage_clears_is_closed(self):
        transition = plan_stage_transition(OpportunityStage.CLOSED_LOST, OpportunityStage.NEGOTIATION)
        self.assertFalse(transition.is_closed)

    def test_moving_between_the_two_closed_stages_stays_closed(self):
        transition = plan_stage_transition(OpportunityStage.CLOSED_WON, OpportunityStage.CLOSED_LOST)
        self.assertTrue(transition.is_closed)


if __name__ == "__main__":
    unittest.main()
