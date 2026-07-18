"""
Pure-logic tests for app/core/text_extraction.py - no DB, no network.
Runnable anywhere a plain Python interpreter is available.

Run standalone with:
    python -m unittest tests.test_text_extraction
"""
import unittest
from dataclasses import dataclass

from app.core.text_extraction import extract_plain_text


@dataclass
class _FakeMessage:
    subject: str | None = None
    body_text: str | None = None
    body_html: str | None = None


class TestExtractPlainText(unittest.TestCase):
    def test_prefers_body_text_when_present(self):
        message = _FakeMessage(subject="Hello", body_text="Plain body", body_html="<p>HTML body</p>")
        self.assertEqual(extract_plain_text(message), "Hello\n\nPlain body")

    def test_falls_back_to_stripped_body_html_when_body_text_missing(self):
        message = _FakeMessage(subject="Hello", body_text=None, body_html="<p>Not <b>interested</b>, thanks.</p>")
        self.assertEqual(extract_plain_text(message), "Hello\n\nNot interested, thanks.")

    def test_falls_back_to_stripped_body_html_when_body_text_blank(self):
        message = _FakeMessage(subject="Hello", body_text="   ", body_html="<p>Yes, let's talk.</p>")
        self.assertEqual(extract_plain_text(message), "Hello\n\nYes, let's talk.")

    def test_decodes_html_entities(self):
        message = _FakeMessage(subject=None, body_html="Tom &amp; Jerry &mdash; sounds good")
        self.assertIn("Tom & Jerry", extract_plain_text(message))

    def test_collapses_whitespace_from_html(self):
        message = _FakeMessage(subject=None, body_html="<div>Line one</div>\n\n\n<div>Line   two</div>")
        result = extract_plain_text(message)
        self.assertNotIn("   ", result)
        self.assertIn("Line one", result)
        self.assertIn("Line two", result)

    def test_no_subject_no_body_returns_empty_string(self):
        message = _FakeMessage(subject=None, body_text=None, body_html=None)
        self.assertEqual(extract_plain_text(message), "")

    def test_subject_only_returns_subject(self):
        message = _FakeMessage(subject="Out of Office", body_text=None, body_html=None)
        self.assertEqual(extract_plain_text(message), "Out of Office")

    def test_body_only_returns_body(self):
        message = _FakeMessage(subject=None, body_text="Interested, let's talk.", body_html=None)
        self.assertEqual(extract_plain_text(message), "Interested, let's talk.")

    def test_blank_subject_is_treated_as_no_subject(self):
        message = _FakeMessage(subject="   ", body_text="Yes", body_html=None)
        self.assertEqual(extract_plain_text(message), "Yes")


if __name__ == "__main__":
    unittest.main()
