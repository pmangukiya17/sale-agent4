"""
Brave Search response -> Discovery candidate mapping - M2 Phase 2's
"Candidate Extraction" step (docs/architecture/m2-discovery-provider-strategy.md
Section 11.2: "turning Brave's page-shaped results into company-shaped
ones"). Deliberately split into its own module, separate from
brave_search.py's own httpx-calling `search()` method, for exactly one
reason: this module has ZERO third-party dependency (stdlib only -
urllib.parse, re), so it is genuinely unit-testable in a sandbox with no
working httpx/PyPI install - see tests/test_brave_search_mapping_pure.py,
which actually executes this logic against a hand-built, doc-shaped
fixture response. brave_search.py's own `search()` method (the part that
makes a real network call) stays UNVERIFIED BY EXECUTION, exactly like
app/delivery/providers/gmail_provider.py before it - see that file's own
docstring for the same disclosed limitation.

Brave's Web Search API returns PAGE-shaped results (title, url,
description) under response["web"]["results"], not already-structured
company records - there is no "company name" field, no "country" field,
no VAT/registration number. Everything below is best-effort heuristic
extraction from a web page's own title/URL/snippet, which is why every
RawProviderResult produced here carries a deliberately modest
provider_confidence (0.45) - much lower than ManualCSVProvider's 1.0
(a human directly typed that data in) - see RawProviderResult's own
docstring for how provider_confidence is used downstream. Nothing here
ever fabricates a field Brave didn't actually provide: no country,
industry, company_size_range, vat_number, registration_number, email, or
contacts are ever guessed - those stay None/[] and are left for a later
provider (OpenCorporates, Phase 3) or a human reviewer to fill in,
exactly as RawProviderResult's own docstring already anticipates
("a real search-derived provider (M2 Phase 2+) may rarely surface
either [identifier]").
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from app.discovery.providers.base import RawProviderResult

# Common suffixes web page titles append after the actual company/site
# name - stripped so `name` is closer to a company name than a full page
# title. Ordered longest-separator-first is unnecessary here since we
# split on the FIRST occurrence of any of these and keep the left side;
# order only matters if a title contains more than one, in which case
# the leftmost split (by position, not list order) wins via the regex
# alternation below.
_TITLE_SEPARATORS = re.compile(r"\s*[|–—-]\s*")


def _clean_title_to_name(title: str) -> str:
    """Best-effort: a web page title like 'Acme Textiles - Home' or
    'Acme Textiles | Wholesale Cotton Yarn Supplier' most often has the
    actual company/site name as its first segment. Falls back to the
    full (whitespace-collapsed) title if splitting would leave nothing
    usable."""
    collapsed = " ".join(title.split())
    if not collapsed:
        return collapsed
    parts = _TITLE_SEPARATORS.split(collapsed, maxsplit=1)
    first = parts[0].strip()
    return first if first else collapsed


def _extract_domain(url: str) -> str | None:
    """Returns a bare, lowercased hostname (no scheme, no leading
    'www.', no path) - the same normalized shape
    app.discovery.normalization.normalize_candidate() already expects
    for `website` on every other provider's output, so a Brave-derived
    candidate dedups against an existing Prospect exactly like any
    other provider's website value would (see app.discovery.dedup's own
    website-exact-match tier)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[len("www."):]
    return host or None


# A page-shaped result missing both a usable title and URL is not a
# candidate at all - nothing meaningful could be extracted from it.
_MIN_CONFIDENCE = 0.45


def extract_candidates(brave_response: dict, *, query: str) -> list[RawProviderResult]:
    """Pure function: a raw Brave Web Search API JSON response in, a list
    of RawProviderResult out. Never raises on a malformed/unexpected
    response shape - returns an empty list instead, since "Brave
    returned something we can't parse" is a legitimate "zero candidates
    from this query variation" outcome for
    app.discovery.search_service.SearchService to handle gracefully,
    not a reason to blow up the whole provider call (see that module's
    own per-variation graceful degradation)."""
    if not isinstance(brave_response, dict):
        return []
    web_section = brave_response.get("web")
    if not isinstance(web_section, dict):
        return []
    results = web_section.get("results")
    if not isinstance(results, list):
        return []

    candidates: list[RawProviderResult] = []
    seen_websites: set[str] = set()

    for entry in results:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        title = entry.get("title")
        if not isinstance(url, str) or not url or not isinstance(title, str) or not title:
            continue

        website = _extract_domain(url)
        name = _clean_title_to_name(title)
        if not name:
            continue

        # Brave frequently returns the same domain more than once across
        # different pages of the same site (e.g. a homepage and a
        # product page) - collapse to the first (usually most relevant,
        # since Brave already ranks its own results) sighting per query
        # variation. Cross-VARIATION and cross-provider duplicates are
        # NOT this function's concern - those are handled by
        # app.discovery.identifier_lookup/app.discovery.dedup at the
        # Prospect level, which already runs uniformly over every
        # provider's output regardless of provider_key.
        if website and website in seen_websites:
            continue
        if website:
            seen_websites.add(website)

        description = entry.get("description") if isinstance(entry.get("description"), str) else None

        candidates.append(
            RawProviderResult(
                name=name,
                raw_payload={"brave_result": entry, "query": query},
                website=website,
                country=None,
                industry_raw=None,
                company_size_range=None,
                description=description,
                source_url=url,
                provider_confidence=_MIN_CONFIDENCE,
                contacts=[],
                vat_number=None,
                registration_number=None,
                email=None,
            )
        )

    return candidates
