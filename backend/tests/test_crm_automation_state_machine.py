"""
Pure-logic tests for app/crm_automation/state_machine.py - no DB, no
network, no fixtures. Unlike this project's *_workflow_e2e.py tests
(which need a real Postgres connection and cannot run in this sandbox),
this test suite exercises real, executable code end to end, because
state_machine.py is deliberately pure - see its own module docstring.

Covers every transition in the approved relationship-stage mapping, the
explicit non-transitions (no rule fired -> stay put), the guarantee that
NEGOTIATION is never reached automatically, and the Task-suggestion
rules' priority order.

Run standalone with:
    python -m unittest tests.test_crm_automation_state_machine
"""
import unittest

from app.crm_automation.state_machine import (
    RelationshipStageTrigger,
    next_relationship_stage,
    suggested_task_for_reply,
)
from app.models.enums import RelationshipStage, ReplyStatus, TaskPriority


class TestNextRelationshipStage(unittest.TestCase):
    # --- the four approved transitions -------------------------------------
    def test_cold_to_contacted_on_outbound_sent(self):
        self.assertEqual(
            next_relationship_stage(RelationshipStage.COLD, RelationshipStageTrigger.OUTBOUND_SENT),
            RelationshipStage.CONTACTED,
        )

    def test_contacted_to_engaged_on_any_inbound_reply(self):
        for status in ReplyStatus:
            with self.subTest(reply_status=status):
                self.assertEqual(
                    next_relationship_stage(
                        RelationshipStage.CONTACTED, RelationshipStageTrigger.INBOUND_REPLY, reply_status=status
                    ),
                    RelationshipStage.ENGAGED,
                    "contacted -> engaged must fire on ANY inbound reply, regardless of classification",
                )

    def test_engaged_to_qualified_only_on_positive(self):
        self.assertEqual(
            next_relationship_stage(
                RelationshipStage.ENGAGED, RelationshipStageTrigger.INBOUND_REPLY, reply_status=ReplyStatus.POSITIVE
            ),
            RelationshipStage.QUALIFIED,
        )

    def test_engaged_stays_put_on_non_positive_replies(self):
        for status in (ReplyStatus.NEGATIVE, ReplyStatus.NEUTRAL, ReplyStatus.OUT_OF_OFFICE):
            with self.subTest(reply_status=status):
                self.assertIsNone(
                    next_relationship_stage(
                        RelationshipStage.ENGAGED, RelationshipStageTrigger.INBOUND_REPLY, reply_status=status
                    )
                )

    def test_qualified_to_negotiation_on_manual_advance_only(self):
        self.assertEqual(
            next_relationship_stage(RelationshipStage.QUALIFIED, RelationshipStageTrigger.MANUAL_ADVANCE),
            RelationshipStage.NEGOTIATION,
        )

    # --- negotiation is never reached automatically ------------------------
    def test_no_trigger_ever_produces_negotiation_except_manual_advance(self):
        automatic_triggers = (RelationshipStageTrigger.OUTBOUND_SENT, RelationshipStageTrigger.INBOUND_REPLY)
        for stage in RelationshipStage:
            for trigger in automatic_triggers:
                for status in list(ReplyStatus) + [None]:
                    with self.subTest(stage=stage, trigger=trigger, reply_status=status):
                        result = next_relationship_stage(stage, trigger, reply_status=status)
                        self.assertNotEqual(
                            result,
                            RelationshipStage.NEGOTIATION,
                            "NEGOTIATION must only ever be reachable via MANUAL_ADVANCE",
                        )

    # --- no-op cases: no rule matches, no transition ------------------------
    def test_outbound_sent_has_no_effect_once_past_cold(self):
        for stage in (
            RelationshipStage.CONTACTED,
            RelationshipStage.ENGAGED,
            RelationshipStage.QUALIFIED,
            RelationshipStage.NEGOTIATION,
        ):
            with self.subTest(stage=stage):
                self.assertIsNone(next_relationship_stage(stage, RelationshipStageTrigger.OUTBOUND_SENT))

    def test_manual_advance_has_no_effect_outside_qualified(self):
        for stage in (
            RelationshipStage.COLD,
            RelationshipStage.CONTACTED,
            RelationshipStage.ENGAGED,
            RelationshipStage.NEGOTIATION,
        ):
            with self.subTest(stage=stage):
                self.assertIsNone(next_relationship_stage(stage, RelationshipStageTrigger.MANUAL_ADVANCE))

    def test_inbound_reply_has_no_effect_on_cold(self):
        # A reply can't arrive before a first outbound touch in this
        # model's own trigger vocabulary - COLD has no inbound_reply rule.
        self.assertIsNone(
            next_relationship_stage(
                RelationshipStage.COLD, RelationshipStageTrigger.INBOUND_REPLY, reply_status=ReplyStatus.POSITIVE
            )
        )


class TestSuggestedTaskForReply(unittest.TestCase):
    def test_needs_human_review_always_wins_and_is_high_priority(self):
        for status in ReplyStatus:
            with self.subTest(reply_status=status):
                suggestion = suggested_task_for_reply(status, needs_human_review=True, advanced_to_qualified=False)
                self.assertIsNotNone(suggestion)
                self.assertEqual(suggestion.priority, TaskPriority.HIGH)
                self.assertEqual(suggestion.source_event_type, "reply_classified")
                self.assertIn(status.value.upper(), suggestion.suggested_action)

    def test_needs_human_review_wins_even_if_also_advanced_to_qualified(self):
        # Real M6.4 mapping never actually produces POSITIVE +
        # needs_human_review=True together, but this function must not
        # assume that invariant - review is still the more urgent signal
        # if it were ever True.
        suggestion = suggested_task_for_reply(ReplyStatus.POSITIVE, needs_human_review=True, advanced_to_qualified=True)
        self.assertEqual(suggestion.source_event_type, "reply_classified")

    def test_advanced_to_qualified_without_review_is_normal_priority(self):
        suggestion = suggested_task_for_reply(ReplyStatus.POSITIVE, needs_human_review=False, advanced_to_qualified=True)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.priority, TaskPriority.NORMAL)
        self.assertEqual(suggestion.source_event_type, "relationship_stage_advanced")

    def test_out_of_office_produces_no_task(self):
        suggestion = suggested_task_for_reply(ReplyStatus.OUT_OF_OFFICE, needs_human_review=False, advanced_to_qualified=False)
        self.assertIsNone(suggestion)

    def test_positive_without_qualification_or_review_produces_no_task(self):
        # e.g. a POSITIVE reply that only advanced CONTACTED -> ENGAGED,
        # not ENGAGED -> QUALIFIED.
        suggestion = suggested_task_for_reply(ReplyStatus.POSITIVE, needs_human_review=False, advanced_to_qualified=False)
        self.assertIsNone(suggestion)


if __name__ == "__main__":
    unittest.main()
