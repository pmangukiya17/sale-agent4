"""
Pure-logic tests for app/reply_intelligence/classifiers/rules_classifier.py
- no DB, no network. Covers every documented example from the M6.4 brief,
the priority order between categories, the needs_human_review mapping,
and that `reason` is always populated.

Run standalone with:
    python -m unittest tests.test_rules_classifier
"""
import unittest

from app.models.enums import ReplyStatus
from app.reply_intelligence.classifiers.base import ReplyClassificationInput
from app.reply_intelligence.classifiers.rules_classifier import RulesReplyClassifier


class TestRulesReplyClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = RulesReplyClassifier()

    def _classify(self, text: str):
        return self.classifier.classify(ReplyClassificationInput(text=text))

    # --- documented examples --------------------------------------------
    def test_out_of_office_subject(self):
        result = self._classify("Out of Office: Re: Quote request\n\nI am currently away from my email.")
        self.assertEqual(result.reply_status, ReplyStatus.OUT_OF_OFFICE)
        self.assertFalse(result.needs_human_review)

    def test_automatic_reply(self):
        result = self._classify("Automatic reply: Quote request\n\nI will be back on Monday.")
        self.assertEqual(result.reply_status, ReplyStatus.OUT_OF_OFFICE)

    def test_not_interested_is_negative(self):
        result = self._classify("Not interested, please remove me from this list.")
        self.assertEqual(result.reply_status, ReplyStatus.NEGATIVE)
        self.assertTrue(result.needs_human_review)

    def test_remove_me_is_negative(self):
        result = self._classify("Remove me from your list, thanks.")
        self.assertEqual(result.reply_status, ReplyStatus.NEGATIVE)

    def test_no_thanks_is_negative(self):
        result = self._classify("No thanks, we're all set.")
        self.assertEqual(result.reply_status, ReplyStatus.NEGATIVE)

    def test_yes_is_positive(self):
        result = self._classify("Yes, that works for me.")
        self.assertEqual(result.reply_status, ReplyStatus.POSITIVE)
        self.assertFalse(result.needs_human_review)

    def test_lets_schedule_is_positive(self):
        result = self._classify("Let's schedule a call next week.")
        self.assertEqual(result.reply_status, ReplyStatus.POSITIVE)

    def test_interested_is_positive(self):
        result = self._classify("I'm interested, tell me more.")
        self.assertEqual(result.reply_status, ReplyStatus.POSITIVE)

    def test_everything_else_is_neutral(self):
        result = self._classify("What is the pricing for the enterprise tier?")
        self.assertEqual(result.reply_status, ReplyStatus.NEUTRAL)
        self.assertTrue(result.needs_human_review)

    def test_empty_text_is_neutral(self):
        result = self._classify("")
        self.assertEqual(result.reply_status, ReplyStatus.NEUTRAL)

    # --- priority order ---------------------------------------------------
    def test_out_of_office_wins_over_incidental_negative_wording(self):
        # An auto-reply body can coincidentally contain phrasing that
        # would otherwise read as NEGATIVE ("not available") - the OOO
        # subject signal must win, not be shadowed by a body scan.
        result = self._classify("Automatic reply: I am not available until Monday.")
        self.assertEqual(result.reply_status, ReplyStatus.OUT_OF_OFFICE)

    def test_negative_wins_over_positive_when_both_present(self):
        result = self._classify("Not interested right now, though it sounds good in theory.")
        self.assertEqual(result.reply_status, ReplyStatus.NEGATIVE)

    # --- needs_human_review mapping, exhaustively -------------------------
    def test_needs_human_review_mapping_for_all_four_categories(self):
        cases = {
            "Yes, let's talk.": (ReplyStatus.POSITIVE, False),
            "Out of Office until Monday.": (ReplyStatus.OUT_OF_OFFICE, False),
            "Not interested, thanks.": (ReplyStatus.NEGATIVE, True),
            "Can you send more details?": (ReplyStatus.NEUTRAL, True),
        }
        for text, (expected_status, expected_review) in cases.items():
            with self.subTest(text=text):
                result = self._classify(text)
                self.assertEqual(result.reply_status, expected_status)
                self.assertEqual(result.needs_human_review, expected_review)

    # --- reason is always populated ---------------------------------------
    def test_reason_is_populated_on_match(self):
        result = self._classify("Yes, interested.")
        self.assertIsNotNone(result.reason)
        self.assertIn("positive", result.reason)

    def test_reason_is_populated_on_neutral_fallthrough(self):
        result = self._classify("Random unrelated text.")
        self.assertIsNotNone(result.reason)

    # --- word-boundary correctness -----------------------------------------
    def test_yes_does_not_match_inside_another_word(self):
        # "yesterday" must not trigger the bare "yes" keyword.
        result = self._classify("I checked yesterday and nothing has changed.")
        self.assertEqual(result.reply_status, ReplyStatus.NEUTRAL)

    def test_case_insensitive_matching(self):
        result = self._classify("NOT INTERESTED")
        self.assertEqual(result.reply_status, ReplyStatus.NEGATIVE)


if __name__ == "__main__":
    unittest.main()
