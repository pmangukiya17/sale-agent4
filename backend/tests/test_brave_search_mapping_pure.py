"""
tests.test_brave_search_mapping_pure - M2 Phase 2.

Genuinely executed in this sandbox: app.discovery.providers.
brave_search_mapping is stdlib-only (urllib.parse, re) - see that
module's own docstring for why it's split out from brave_search.py's own
httpx-calling search() method, which stays UNVERIFIED BY EXECUTION.
Fixture response below is hand-built to match Brave's own published Web
Search API response shape (response.web.results[].{title,url,description})
per https://api-dashboard.search.brave.com/documentation/web-search.

Run standalone with:
    python -m unittest tests.test_brave_search_mapping_pure
"""
import unittest

from app.discovery.providers.brave_search_mapping import extract_candidates


def _brave_response(*entries: dict) -> dict:
    return {"web": {"results": list(entries)}}


class TestExtractCandidates(unittest.TestCase):
    def test_basic_extraction(self):
        response = _brave_response(
            {
                "title": "Acme Textiles - Home",
                "url": "https://www.acmetextiles.example.com/",
                "description": "Leading cotton yarn supplier since 1990.",
            }
        )
        candidates = extract_candidates(response, query="cotton yarn supplier")
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.name, "Acme Textiles")
        self.assertEqual(candidate.website, "acmetextiles.example.com")
        self.assertEqual(candidate.source_url, "https://www.acmetextiles.example.com/")
        self.assertEqual(candidate.description, "Leading cotton yarn supplier since 1990.")
        self.assertAlmostEqual(candidate.provider_confidence, 0.45)
        self.assertEqual(candidate.contacts, [])
        self.assertIsNone(candidate.country)
        self.assertIsNone(candidate.vat_number)
        self.assertIsNone(candidate.registration_number)
        self.assertIsNone(candidate.email)
        self.assertEqual(candidate.raw_payload["query"], "cotton yarn supplier")

    def test_title_separator_variants_all_split_correctly(self):
        cases = {
            "Acme Textiles | Wholesale Cotton Yarn Supplier": "Acme Textiles",
            "Acme Textiles - Wholesale Cotton Yarn Supplier": "Acme Textiles",
            "Acme Textiles – Wholesale Cotton Yarn Supplier": "Acme Textiles",  # en dash
        }
        for title, expected_name in cases.items():
            with self.subTest(title=title):
                response = _brave_response({"title": title, "url": "https://acme.example.com/"})
                candidates = extract_candidates(response, query="q")
                self.assertEqual(candidates[0].name, expected_name)

    def test_title_with_no_separator_keeps_full_title(self):
        response = _brave_response({"title": "Acme Textiles Wholesale Supplier", "url": "https://acme.example.com/"})
        candidates = extract_candidates(response, query="q")
        self.assertEqual(candidates[0].name, "Acme Textiles Wholesale Supplier")

    def test_www_prefix_is_stripped_from_website(self):
        response = _brave_response({"title": "Acme", "url": "https://www.acme.example.com/products"})
        candidates = extract_candidates(response, query="q")
        self.assertEqual(candidates[0].website, "acme.example.com")

    def test_missing_title_or_url_is_skipped(self):
        response = _brave_response(
            {"title": "No URL Here"},
            {"url": "https://noturl.example.com/"},
            {"title": "", "url": "https://empty-title.example.com/"},
        )
        candidates = extract_candidates(response, query="q")
        self.assertEqual(candidates, [])

    def test_duplicate_website_within_one_response_collapses_to_first(self):
        response = _brave_response(
            {"title": "Acme Home", "url": "https://acme.example.com/"},
            {"title": "Acme Products Page", "url": "https://acme.example.com/products"},
        )
        candidates = extract_candidates(response, query="q")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].name, "Acme Home")

    def test_missing_web_section_returns_empty_list(self):
        self.assertEqual(extract_candidates({}, query="q"), [])
        self.assertEqual(extract_candidates({"web": "not-a-dict"}, query="q"), [])
        self.assertEqual(extract_candidates({"web": {"results": "not-a-list"}}, query="q"), [])

    def test_malformed_response_never_raises(self):
        self.assertEqual(extract_candidates(None, query="q"), [])  # type: ignore[arg-type]
        self.assertEqual(extract_candidates("not-a-dict", query="q"), [])  # type: ignore[arg-type]
        self.assertEqual(extract_candidates(_brave_response("not-a-dict-entry"), query="q"), [])

    def test_raw_payload_preserves_the_original_entry(self):
        entry = {"title": "Acme", "url": "https://acme.example.com/", "age": "2 days ago"}
        response = _brave_response(entry)
        candidates = extract_candidates(response, query="q")
        self.assertEqual(candidates[0].raw_payload["brave_result"], entry)


if __name__ == "__main__":
    unittest.main()
