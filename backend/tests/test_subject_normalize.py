"""
Pure-logic tests for app/reply_intelligence/subject_normalize.py - no DB,
no network. Runnable anywhere a plain Python interpreter is available.

Run standalone with:
    python -m unittest tests.test_subject_normalize
"""
import unittest

from app.reply_intelligence.subject_normalize import normalize_subject


class TestNormalizeSubject(unittest.TestCase):
    def test_none_returns_empty_string(self):
        self.assertEqual(normalize_subject(None), "")

    def test_empty_string_returns_empty_string(self):
        self.assertEqual(normalize_subject(""), "")

    def test_plain_subject_is_lowercased_and_trimmed(self):
        self.assertEqual(normalize_subject("  Quote Request  "), "quote request")

    def test_single_re_prefix_stripped(self):
        self.assertEqual(normalize_subject("Re: Quote request"), "quote request")

    def test_single_fwd_prefix_stripped(self):
        self.assertEqual(normalize_subject("Fwd: Quote request"), "quote request")
        self.assertEqual(normalize_subject("FW: Quote request"), "quote request")

    def test_repeated_mixed_prefixes_all_stripped(self):
        self.assertEqual(normalize_subject("Re: Fwd: RE: Quote request"), "quote request")

    def test_prefix_matching_is_case_insensitive(self):
        self.assertEqual(normalize_subject("rE: quote request"), "quote request")

    def test_subject_without_any_prefix_unchanged_besides_casing(self):
        self.assertEqual(normalize_subject("Quote Request"), "quote request")

    def test_two_different_subjects_normalize_differently(self):
        self.assertNotEqual(normalize_subject("Re: Quote request"), normalize_subject("Re: Invoice question"))


if __name__ == "__main__":
    unittest.main()
