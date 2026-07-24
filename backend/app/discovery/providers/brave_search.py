"""
BraveSearchProvider - M2 Phase 2's first query-driven ("search-type")
provider, per docs/architecture/m2-discovery-provider-strategy.md
Sections 1-2/11 (CEO-approved: "Brave Search API, not because it's the
default, but because it's the last one standing" after Bing's August
2025 retirement and Google Custom Search's confirmed shutdown clock).

Called ONLY by app.discovery.search_service.SearchService - never
directly by app.discovery.pipeline. See registry.py's own
SEARCH_PROVIDER_KEYS/DIRECT_PROVIDER_KEYS split and
search_service.py's docstring for the full reasoning; the short version:
a query-driven provider has no single `query_spec` naturally supplied by
a DiscoverySearch row the way ManualCSVProvider's `rows` are - it needs a
QueryPlan (app.discovery.query_planner) built from the business's own
Products/ICP first, and its raw web-page results need "Candidate
Extraction" (turning a page into a company) before they look like every
other provider's output - both of those are the Search Service's job,
not this class's.

query_spec here is always ONE query variation's dict
(app.discovery.query_planner.QueryVariation.as_query_spec()) - the
Search Service calls search() once per variation, never once per whole
plan, so this method's job is narrow: issue one Brave Search API call
(with its own internal timeout+retry policy, see settings.
BRAVE_SEARCH_TIMEOUT_SECONDS/BRAVE_SEARCH_MAX_RETRIES), and turn the
page-shaped JSON response into company-shaped RawProviderResult
candidates via the pure, separately-tested
app.discovery.providers.brave_search_mapping.extract_candidates() - see
that module's own docstring for why response-parsing lives there and not
here.

UNVERIFIED BY EXECUTION: like app/delivery/providers/gmail_provider.py
before it, this file has never been run against the real Brave Search
API - this sandbox has neither network access to install httpx nor a
real Brave Search API key to test against (no PyPI/network access at
all - a disclosed, standing constraint of this project's authoring
environment, confirmed again this phase via a failed `pip install
httpx`). Verified here only via py_compile and manual cross-reference
against Brave's own published Web Search API documentation
(https://api-dashboard.search.brave.com/documentation/web-search:
`X-Subscription-Token` header, `q`/`count`/`country`/`search_lang` query
parameters, `response.web.results[].{title,url,description}` response
shape). Needs a real run against a real Brave Search API subscription
before being trusted in production - see verify_m2_phase2.sh's own
disclosed-gaps section.
"""
import time
from typing import Any

import httpx

from app.core.config import settings
from app.discovery.context import DiscoveryContext
from app.discovery.providers.base import (
    DiscoveryProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderSearchOutcome,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.discovery.providers.brave_search_mapping import extract_candidates


class BraveSearchProvider(DiscoveryProvider):
    key = "brave_search"

    def provider_name(self) -> str:
        return "Brave Search"

    def health(self) -> bool:
        """Cheap, no-network readiness check - see base.py's own
        docstring for the convention this follows.
        settings.BRAVE_SEARCH_ENABLED is a separate, explicit operator
        kill switch from "is a key configured" - see
        app.core.config.Settings' own comment for why these are
        deliberately two flags, not one."""
        return bool(settings.BRAVE_SEARCH_ENABLED and settings.BRAVE_SEARCH_API_KEY)

    def capabilities(self) -> dict[str, Any]:
        return {
            "query_driven": True,
            "supports_country_filter": True,
            "supports_language_filter": True,
            # Page-shaped web results, not structured company records -
            # see brave_search_mapping.py's own docstring for why every
            # candidate this provider produces leaves country/industry/
            # company_size_range/identifiers as None rather than guessing.
            "returns_structured_company_data": False,
            "returns_contacts": False,
        }

    def search(self, query_spec: dict[str, Any], context: DiscoveryContext) -> ProviderSearchOutcome:
        if not self.health():
            raise ProviderAuthError(
                "BraveSearchProvider is not configured - set BRAVE_SEARCH_API_KEY "
                "(and confirm BRAVE_SEARCH_ENABLED is true) before enabling 'brave_search' on a search."
            )

        query = (query_spec or {}).get("query")
        if not query:
            raise ProviderError("brave_search provider expects query_spec['query'] to be a non-empty string")

        params: dict[str, Any] = {"q": query, "count": 20}
        country = query_spec.get("country")
        if country:
            params["country"] = country
        language = query_spec.get("language")
        if language:
            params["search_lang"] = language

        max_attempts = 1 + max(0, settings.BRAVE_SEARCH_MAX_RETRIES)
        last_error: ProviderError | None = None

        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                # Small, bounded backoff between retries only - never on
                # the first attempt. Capped low (Discovery jobs already
                # run synchronously inside one Step Runner worker tick -
                # see app.discovery.pipeline's own docstring - so an
                # unbounded backoff here would eat into that tick's own
                # time budget for no real benefit).
                time.sleep(min(0.5 * (2 ** (attempt - 2)), 4.0))

            try:
                response = httpx.get(
                    settings.BRAVE_SEARCH_BASE_URL,
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": settings.BRAVE_SEARCH_API_KEY,
                    },
                    timeout=settings.BRAVE_SEARCH_TIMEOUT_SECONDS,
                )
            except httpx.TimeoutException as exc:
                last_error = ProviderTimeoutError(
                    f"Brave Search request timed out (attempt {attempt}/{max_attempts}): {exc}"
                )
                continue
            except httpx.HTTPError as exc:
                last_error = ProviderUnavailableError(
                    f"Brave Search request failed (attempt {attempt}/{max_attempts}): {exc}"
                )
                continue

            if response.status_code in (401, 403):
                # Never worth retrying - the same credentials will be
                # rejected identically on every attempt.
                raise ProviderAuthError(
                    f"Brave Search rejected the API key ({response.status_code}): {response.text[:200]}"
                )
            if response.status_code == 429:
                last_error = ProviderRateLimitError(
                    f"Brave Search rate limit hit (attempt {attempt}/{max_attempts}): {response.text[:200]}"
                )
                continue
            if response.status_code >= 500:
                last_error = ProviderUnavailableError(
                    f"Brave Search server error {response.status_code} "
                    f"(attempt {attempt}/{max_attempts}): {response.text[:200]}"
                )
                continue
            if response.status_code >= 400:
                # A 4xx other than 401/403/429 is almost always a
                # malformed request on OUR side - not worth retrying
                # identically.
                raise ProviderError(f"Brave Search rejected the request ({response.status_code}): {response.text[:200]}")

            try:
                data = response.json()
            except ValueError as exc:
                last_error = ProviderUnavailableError(
                    f"Brave Search returned unparseable JSON (attempt {attempt}/{max_attempts}): {exc}"
                )
                continue

            candidates = extract_candidates(data, query=query)
            return ProviderSearchOutcome(results=candidates, request_count=1, api_cost=None, token_usage=None)

        raise last_error or ProviderUnavailableError(
            "Brave Search failed with no captured error - this branch should be unreachable"
        )
