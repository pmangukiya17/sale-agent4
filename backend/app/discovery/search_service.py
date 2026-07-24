"""
Search Service - M2 Phase 2: External Research Provider Framework.

Per docs/architecture/m2-discovery-provider-strategy.md Section 11.1
(CEO-approved refinement): the Discovery Pipeline must never directly
depend on a query-driven ("search-type") provider's own specifics
(query construction, pagination, provider-specific rate limits,
candidate extraction from a page-shaped response). This module is the
one abstraction layer that sits between app.discovery.pipeline and
every such provider - pipeline.py calls exactly one method here,
`discover(provider_key, query_plan, context)`, and never imports
BraveSearchProvider (or any future query-driven provider) directly. See
app.discovery.providers.registry's own SEARCH_PROVIDER_KEYS/
DIRECT_PROVIDER_KEYS split for which providers are routed through here
versus called directly (manual_csv, row-driven, stays outside this
module entirely - it has no query to plan).

Architecture requirement satisfied: "The Discovery Pipeline must never
call provider-specific code directly" - pipeline.py's own diff for this
phase (see that module's docstring) adds exactly one branch
(`is_search_provider(provider_key)`) and one call
(`search_service.discover(...)`), never a reference to
`BraveSearchProvider` or `httpx` anywhere in pipeline.py.

Per-variation graceful degradation: one query variation failing (say, a
transient timeout on one of ten query strings a Query Planner produced)
does not fail the whole provider for this job - only EVERY variation
failing raises ProviderError, which app.discovery.pipeline's existing
per-provider try/except already understands (log it, record a failed
DiscoveryJobProviderRun, continue to the next provider_key - unchanged
by this phase). This is a finer granularity than that existing
job-level "one provider's failure doesn't fail the whole job" guarantee,
layered on top of it, not a replacement for it.

`provider_lookup` constructor param is a deliberate testability seam,
copied directly from app.ai_gateway.client.AIGateway's own precedent
(see that class's docstring for the identical reasoning). Every
concrete query-driven provider (BraveSearchProvider today) imports a
third-party HTTP library at module level, which this project's
authoring sandbox cannot install (no PyPI/network access - a disclosed,
standing constraint). Resolving the real provider registry only
lazily, inside `_resolve_provider()`, means merely importing this
module - or unit testing SearchService's own retry/merge/error-handling
logic via a fake provider passed as `provider_lookup` - never requires
httpx to be installed. See tests/test_search_service_pure.py, which
exercises this class for real, in this sandbox, using exactly that seam.

`from __future__ import annotations` + a TYPE_CHECKING-only
DiscoveryContext import, for the identical reason
app/discovery/providers/base.py now does the same (see that module's own
docstring) - this class only ever passes `context` through to a
provider's own search() call, never inspects it directly, so the type
is needed for annotations only, never at runtime.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

from app.discovery.providers.base import DiscoveryProvider, ProviderError, ProviderSearchOutcome
from app.discovery.query_planner import QueryPlan

if TYPE_CHECKING:
    from app.discovery.context import DiscoveryContext

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, provider_lookup: Optional[Callable[[str], DiscoveryProvider]] = None):
        self._provider_lookup = provider_lookup

    def _resolve_provider(self, provider_key: str) -> DiscoveryProvider:
        if self._provider_lookup is not None:
            return self._provider_lookup(provider_key)
        from app.discovery.providers.registry import get_provider

        return get_provider(provider_key)

    def discover(self, provider_key: str, query_plan: QueryPlan, context: DiscoveryContext) -> ProviderSearchOutcome:
        # KeyError (unknown provider_key) bubbles up unchanged - the
        # exact same contract app.discovery.pipeline already handles
        # today for get_provider() on a direct provider, so no new
        # exception-handling branch is needed there for this path either.
        provider = self._resolve_provider(provider_key)

        if not provider.health():
            raise ProviderError(
                f"Provider '{provider_key}' is disabled or not configured (health() returned False) - "
                f"check its required settings (e.g. an API key) before enabling it on a search."
            )

        if not query_plan.variations:
            # A business with no active Products (or no ICP dimensions
            # configured yet) legitimately yields an empty QueryPlan -
            # see app.discovery.query_planner.build_query_plan()'s own
            # docstring. "Nothing to search for" is not an error.
            logger.info("search_service.empty_query_plan", extra={"provider_key": provider_key})
            return ProviderSearchOutcome(results=[], request_count=0, api_cost=0, token_usage=None)

        merged_results = []
        total_requests = 0
        total_cost = 0.0
        cost_seen = False
        total_tokens = 0
        tokens_seen = False
        variation_errors: list[str] = []

        for variation in query_plan.variations:
            try:
                outcome = provider.search(variation.as_query_spec(), context)
            except ProviderError as exc:
                variation_errors.append(f"{variation.query!r}: {exc}")
                logger.warning(
                    "search_service.variation_failed",
                    extra={"provider_key": provider_key, "query": variation.query, "error": str(exc)},
                )
                continue

            merged_results.extend(outcome.results)
            total_requests += outcome.request_count
            if outcome.api_cost is not None:
                total_cost += outcome.api_cost
                cost_seen = True
            if outcome.token_usage is not None:
                total_tokens += outcome.token_usage
                tokens_seen = True

        if not merged_results and variation_errors and len(variation_errors) == len(query_plan.variations):
            # Every variation failed - this provider genuinely produced
            # nothing usable this job. Raise so app.discovery.pipeline's
            # existing per-provider try/except records it as a failed
            # DiscoveryJobProviderRun, exactly like an unconfigured/
            # unknown provider already does - "some results, some
            # failures" is NOT this branch (that's graceful degradation,
            # handled above by simply continuing); this is "zero results
            # AND every attempt errored."
            raise ProviderError(
                f"All {len(query_plan.variations)} query variation(s) failed for provider '{provider_key}': "
                + "; ".join(variation_errors[:5])
                + (" ..." if len(variation_errors) > 5 else "")
            )

        return ProviderSearchOutcome(
            results=merged_results,
            request_count=total_requests,
            api_cost=total_cost if cost_seen else None,
            token_usage=total_tokens if tokens_seen else None,
        )


# Shared default instance - the call shape app.discovery.pipeline
# actually uses (no per-request state to isolate; SearchService itself
# holds no mutable state beyond the constructor-time provider_lookup
# seam). Tests that need a fake provider construct their OWN
# SearchService(provider_lookup=...) directly instead of using this
# module-level function - see tests/test_search_service_pure.py.
_default_search_service = SearchService()


def discover(provider_key: str, query_plan: QueryPlan, context: DiscoveryContext) -> ProviderSearchOutcome:
    return _default_search_service.discover(provider_key, query_plan, context)
