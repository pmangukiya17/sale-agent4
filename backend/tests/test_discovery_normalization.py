"""
tests.test_discovery_normalization - M2 Phase 1a (+ Phase 1b's
normalize_vat_number/normalize_registration_number additions).

Pure logic, zero fixtures, zero database - app/discovery/normalization.py
imports nothing beyond dedup.py's now-safely-importable pure functions
(see tests.test_discovery_dedup_pure's own docstring), so this whole
suite runs to completion with no sqlalchemy/Postgres/Docker access, same
as tests/test_scope_utils.py.
"""
import unittest

from app.discovery.normalization import (
    IndustryRef,
    normalize_candidate,
    normalize_country,
    normalize_registration_number,
    normalize_vat_number,
    resolve_industry,
)


class TestNormalizeCountry(unittest.TestCase):
    def test_expands_known_alias(self):
        self.assertEqual(normalize_country("USA"), "United States")
        self.assertEqual(normalize_country("uk"), "United Kingdom")
        self.assertEqual(normalize_country("uae"), "United Arab Emirates")

    def test_unknown_country_passes_through_cleaned(self):
        self.assertEqual(normalize_country("  Germany  "), "Germany")

    def test_none_and_empty(self):
        self.assertIsNone(normalize_country(None))
        self.assertIsNone(normalize_country("   "))


class TestNormalizeVatNumber(unittest.TestCase):
    """M2 Phase 1b."""

    def test_uppercases_and_strips_separators(self):
        self.assertEqual(normalize_vat_number("de 123 456 789"), "DE123456789")
        self.assertEqual(normalize_vat_number("DE-123-456-789"), "DE123456789")

    def test_equivalent_forms_normalize_identically(self):
        self.assertEqual(normalize_vat_number("DE 123.456.789"), normalize_vat_number("de123456789"))

    def test_none_and_empty_and_whitespace_only(self):
        self.assertIsNone(normalize_vat_number(None))
        self.assertIsNone(normalize_vat_number(""))
        self.assertIsNone(normalize_vat_number("   "))


class TestNormalizeRegistrationNumber(unittest.TestCase):
    """M2 Phase 1b - separate identifier type from VAT, same cleanup
    logic today (see normalize_registration_number's own docstring for
    why it's still a distinct function)."""

    def test_uppercases_and_strips_separators(self):
        self.assertEqual(normalize_registration_number("hrb 12345"), "HRB12345")

    def test_none_and_empty(self):
        self.assertIsNone(normalize_registration_number(None))
        self.assertIsNone(normalize_registration_number(""))


class TestResolveIndustry(unittest.TestCase):
    def setUp(self):
        self.known = [
            IndustryRef(id="ind-1", name="Textiles"),
            IndustryRef(id="ind-2", name="Software"),
        ]

    def test_exact_match(self):
        industry_id, method = resolve_industry("Textiles", self.known)
        self.assertEqual(industry_id, "ind-1")
        self.assertEqual(method, "exact")

    def test_exact_match_case_and_suffix_insensitive(self):
        industry_id, method = resolve_industry("textiles", self.known)
        self.assertEqual(industry_id, "ind-1")
        self.assertEqual(method, "exact")

    def test_keyword_match_substring(self):
        industry_id, method = resolve_industry("Textiles & Apparel", self.known)
        self.assertEqual(industry_id, "ind-1")
        self.assertEqual(method, "keyword")

    def test_no_match_returns_none_none(self):
        industry_id, method = resolve_industry("Aerospace", self.known)
        self.assertIsNone(industry_id)
        self.assertIsNone(method)

    def test_empty_raw_or_no_known_industries(self):
        self.assertEqual(resolve_industry(None, self.known), (None, None))
        self.assertEqual(resolve_industry("Textiles", []), (None, None))


class TestNormalizeCandidate(unittest.TestCase):
    def test_full_candidate_normalizes_every_field(self):
        known = [IndustryRef(id="ind-1", name="Textiles")]
        result = normalize_candidate(
            name="  Acme Textiles GmbH  ",
            website="HTTPS://WWW.Acme-Textiles.COM/",
            country="usa",
            industry_raw="Textiles Importing",
            company_size_range="  51-200  ",
            description="A textile importer.",
            known_industries=known,
            vat_number="de 123 456 789",
            registration_number="hrb 12345",
            email="  contact@acme-textiles.com  ",
        )
        # Display name is whitespace-cleaned only - never lowercased or
        # suffix-stripped like the internal dedup comparison key is.
        self.assertEqual(result.name, "Acme Textiles GmbH")
        self.assertEqual(result.website, "acme-textiles.com")
        self.assertEqual(result.country, "United States")
        self.assertEqual(result.industry_id, "ind-1")
        self.assertEqual(result.industry_match_method, "keyword")
        self.assertEqual(result.industry_raw, "Textiles Importing")
        self.assertEqual(result.company_size_range, "51-200")
        self.assertEqual(result.vat_number, "DE123456789")
        self.assertEqual(result.registration_number, "HRB12345")
        self.assertEqual(result.email, "contact@acme-textiles.com")

    def test_identifier_fields_default_to_none(self):
        # Every existing caller that doesn't pass vat_number/
        # registration_number/email must keep working unchanged.
        result = normalize_candidate(
            name="Acme", website=None, country=None, industry_raw=None,
            company_size_range=None, description=None,
        )
        self.assertIsNone(result.vat_number)
        self.assertIsNone(result.registration_number)
        self.assertIsNone(result.email)

    def test_unresolved_industry_is_kept_verbatim_not_discarded(self):
        result = normalize_candidate(
            name="Acme Aerospace",
            website=None,
            country=None,
            industry_raw="Aerospace",
            company_size_range=None,
            description=None,
            known_industries=[IndustryRef(id="ind-1", name="Textiles")],
        )
        self.assertIsNone(result.industry_id)
        self.assertIsNone(result.industry_match_method)
        self.assertEqual(result.industry_raw, "Aerospace")

    def test_as_payload_shape(self):
        result = normalize_candidate(
            name="Acme", website=None, country=None, industry_raw=None,
            company_size_range=None, description=None,
        )
        payload = result.as_payload()
        self.assertEqual(
            set(payload.keys()),
            {"name", "website", "country", "industry_raw", "industry_id",
             "industry_match_method", "company_size_range", "description",
             "vat_number", "registration_number", "email"},
        )


if __name__ == "__main__":
    unittest.main()
