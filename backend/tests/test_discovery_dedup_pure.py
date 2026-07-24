"""
tests.test_discovery_dedup_pure - M2 Phase 1a.

Pure logic, zero fixtures, zero database. app/discovery/dedup.py's
normalize_website()/normalize_company_name()/name_similarity() never
touched sqlalchemy at runtime, but the module's top-level `from
app.models.prospect import Prospect` import meant it could never be
imported at all without a working sqlalchemy install - so these
functions had never actually been run in this sandbox before, despite
being pure. Phase 1a moved that import behind `TYPE_CHECKING` (see
dedup.py's own docstring) specifically so this module - and
app/discovery/normalization.py, which reuses these same two functions -
could be genuinely unit-tested, the same "pure logic, actually executed
in the authoring sandbox" precedent tests/test_scope_utils.py and
tests/test_opportunity_state_machine.py already set.

find_duplicate() itself still isn't covered here - it operates on real
Prospect ORM rows and needs a database, so it stays covered only by the
existing DB-backed e2e suite (tests/test_discovery_workflow_e2e.py).
"""
import unittest

from app.discovery.dedup import name_similarity, normalize_company_name, normalize_website


class TestNormalizeWebsite(unittest.TestCase):
    def test_strips_scheme_and_www(self):
        self.assertEqual(normalize_website("https://www.Example.com/"), "example.com")

    def test_strips_trailing_slash_no_scheme(self):
        self.assertEqual(normalize_website("example.com/"), "example.com")

    def test_none_and_empty_return_none(self):
        self.assertIsNone(normalize_website(None))
        self.assertIsNone(normalize_website(""))

    def test_two_equivalent_urls_normalize_identically(self):
        self.assertEqual(
            normalize_website("HTTPS://WWW.Acme-Textiles.COM/"),
            normalize_website("acme-textiles.com"),
        )


class TestNormalizeCompanyName(unittest.TestCase):
    def test_strips_legal_suffix_and_lowercases(self):
        self.assertEqual(normalize_company_name("Acme Textiles GmbH"), "acme textiles")

    def test_strips_punctuation(self):
        self.assertEqual(normalize_company_name("Acme, Textiles & Co."), "acme textiles")

    def test_empty_and_none(self):
        self.assertEqual(normalize_company_name(None), "")
        self.assertEqual(normalize_company_name(""), "")


class TestNameSimilarity(unittest.TestCase):
    def test_identical_names_score_one(self):
        self.assertEqual(name_similarity("Acme Textiles", "Acme Textiles"), 1.0)

    def test_legal_suffix_difference_still_scores_high(self):
        # This is the exact case DEFINITE_MATCH_THRESHOLD (0.85) exists
        # for - the same real company, one source includes the legal
        # suffix and the other doesn't.
        score = name_similarity("Acme Textiles GmbH", "Acme Textiles")
        self.assertGreaterEqual(score, 0.85)

    def test_genuinely_different_names_score_low(self):
        score = name_similarity("Acme Textiles", "Global Widgets Inc")
        self.assertLess(score, 0.6)


if __name__ == "__main__":
    unittest.main()
