"""
tests.test_discovery_validation - M2 Phase 1a.

Pure logic, zero fixtures, zero database - app/discovery/validation.py
imports nothing beyond the stdlib, so this whole suite runs to
completion with no sqlalchemy/Postgres/Docker access, same as
tests/test_scope_utils.py.
"""
import unittest

from app.discovery.validation import (
    check_country_known,
    check_domain_syntax,
    check_name_quality,
    check_required_fields,
    check_website_reachable,
    validate_candidate,
)


class TestCheckRequiredFields(unittest.TestCase):
    def test_name_plus_website_passes(self):
        self.assertTrue(check_required_fields("Acme", "acme.com", None).passed)

    def test_name_plus_country_passes(self):
        self.assertTrue(check_required_fields("Acme", None, "Germany").passed)

    def test_missing_name_fails(self):
        self.assertFalse(check_required_fields(None, "acme.com", "Germany").passed)

    def test_name_alone_with_nothing_else_fails(self):
        self.assertFalse(check_required_fields("Acme", None, None).passed)


class TestCheckNameQuality(unittest.TestCase):
    def test_real_name_passes(self):
        self.assertTrue(check_name_quality("Acme Textiles GmbH").passed)

    def test_empty_name_fails(self):
        self.assertFalse(check_name_quality("").passed)
        self.assertFalse(check_name_quality(None).passed)

    def test_boilerplate_name_fails(self):
        self.assertFalse(check_name_quality("Home | Sitemap").passed)
        self.assertFalse(check_name_quality("Page Not Found").passed)

    def test_single_character_fails(self):
        self.assertFalse(check_name_quality("A").passed)


class TestCheckDomainSyntax(unittest.TestCase):
    def test_valid_domain_passes(self):
        self.assertTrue(check_domain_syntax("acme-textiles.com").passed)

    def test_no_website_passes_by_default(self):
        self.assertTrue(check_domain_syntax(None).passed)

    def test_garbage_string_fails(self):
        self.assertFalse(check_domain_syntax("not a domain at all").passed)
        self.assertFalse(check_domain_syntax("just_text").passed)


class TestCheckCountryKnown(unittest.TestCase):
    def test_known_country_passes(self):
        result = check_country_known("Germany", known_countries={"Germany", "France"})
        self.assertTrue(result.passed)

    def test_unknown_country_fails(self):
        result = check_country_known("Atlantis", known_countries={"Germany", "France"})
        self.assertFalse(result.passed)

    def test_no_known_list_supplied_skips_not_fails(self):
        result = check_country_known("Atlantis", known_countries=None)
        self.assertTrue(result.passed)

    def test_no_country_passes(self):
        self.assertTrue(check_country_known(None, known_countries={"Germany"}).passed)


class TestCheckWebsiteReachable(unittest.TestCase):
    def test_no_checker_wired_skips_not_fails(self):
        # Phase 1 default - no network-calling provider exists yet, so
        # this must never silently fail every candidate.
        result = check_website_reachable("acme.com")
        self.assertTrue(result.passed)
        self.assertIn("not attempted", result.detail)

    def test_injected_checker_true(self):
        result = check_website_reachable("acme.com", reachability_checker=lambda url: True)
        self.assertTrue(result.passed)

    def test_injected_checker_false(self):
        result = check_website_reachable("dead-domain.com", reachability_checker=lambda url: False)
        self.assertFalse(result.passed)

    def test_injected_checker_raises_is_treated_as_skipped(self):
        def _boom(url):
            raise ConnectionError("timeout")

        result = check_website_reachable("acme.com", reachability_checker=_boom)
        self.assertTrue(result.passed)  # a broken checker must never fail a discovery job


class TestValidateCandidate(unittest.TestCase):
    def test_well_formed_candidate_passes_overall(self):
        result = validate_candidate(name="Acme Textiles GmbH", website="acme-textiles.com", country="Germany")
        self.assertTrue(result.passed)
        self.assertEqual(len(result.checks), 5)

    def test_bad_candidate_fails_overall_with_reasons(self):
        result = validate_candidate(name="Home", website="not a domain", country=None)
        self.assertFalse(result.passed)
        failed_checks = [c for c in result.checks if not c.passed]
        self.assertGreaterEqual(len(failed_checks), 2)
        for c in failed_checks:
            self.assertIsNotNone(c.detail)  # never a bare pass/fail with no reason

    def test_duplicate_confidence_is_not_a_validation_concern(self):
        # Explicit regression guard for the CEO's own corrected design:
        # duplicate-confidence must never appear as a check name here -
        # it belongs exclusively to app.discovery.dedup.
        result = validate_candidate(name="Acme", website="acme.com", country="Germany")
        check_names = {c.check for c in result.checks}
        self.assertNotIn("duplicate_confidence", check_names)

    def test_as_payload_shape(self):
        result = validate_candidate(name="Acme", website="acme.com", country="Germany")
        payload = result.as_payload()
        self.assertIn("passed", payload)
        self.assertIn("checks", payload)
        self.assertEqual(len(payload["checks"]), 5)


if __name__ == "__main__":
    unittest.main()
