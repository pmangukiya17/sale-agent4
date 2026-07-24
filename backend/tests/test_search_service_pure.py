"""
tests.test_search_service_pure - M2 Phase 2.

Genuinely executed in this sandbox: app.discovery.search_service imports
nothing that requires sqlalchemy or httpx at runtime (see that module's
own docstring, and app/discovery/providers/base.py's matching
TYPE_CHECKING-only DiscoveryContext import). Every test below injects a
FakeProvider via SearchService's own `provider_lookup` constructor
seam - the identical testability pattern
app.ai_gateway.client.AIGateway's own tests already rely on - so none of
these tests need a real BraveSearchProvider, a real network call, or a
real database. Covers every category the CEO's own Phase 2 spec asked
for: provider registry resolution (via provider_lookup, a stand-in for
the real one in app.discovery.providers.registry), the provider
interface (health()/search() contract), successful execution, a
timeout-shaped failure, a generic exception, multiple providers,
duplicate results across providers, a disabled provider, and graceful
degradation.

Run standalone with:
    python -m unittest tests.test_search_service_pure
"""
import unittest

from app.discovery.providers.base import (
    ProviderError,
    ProviderSearchOutcome,
    ProviderTimeoutError,
    RawProviderResult,
)
from app.discovery.query_planner import QueryPlan, QueryVariation
from app.discovery.search_service import SearchService


class FakeProvider:
    """Duck-typed stand-in for a real DiscoveryProvider - SearchService
    only ever calls .health() and .search(query_spec, context) on
    whatever `provider_lookup` returns, so a fake needs nothing more than
    that to be a faithful test double."""

    def __init__(self, *, healthy: bool = True, response_by_query: dict | None = None, default_error: Exception | None = None):
        self.healthy = healthy
        self.response_by_query = response_by_query or {}
        self.default_error = default_error
        self.calls: list[str] = []

    def health(self) -> bool:
        return self.healthy

    def search(self, query_spec: dict, context) -> ProviderSearchOutcome:
        query = query_spec["query"]
        self.calls.append(query)
        if query in self.response_by_query:
            result = self.response_by_query[query]
            if isinstance(result, Exception):
                raise result
            return result
        if self.default_error is not None:
            raise self.default_error
        return ProviderSearchOutcome(results=[], request_count=1, api_cost=0.001, token_usage=None)


def _outcome_with_one_result(name: str, website: str) -> ProviderSearchOutcome:
    return ProviderSearchOutcome(
        results=[RawProviderResult(name=name, raw_payload={"name": name}, website=website, provider_confidence=0.5)],
        request_count=1,
        api_cost=0.002,
        token_usage=None,
    )


def _plan(*queries: str) -> QueryPlan:
    return QueryPlan(variations=[QueryVariation(query=q) for q in queries])


class TestProviderLookupAndRegistrySeam(unittest.TestCase):
    """'Provider registry' category - SearchService resolves providers
    via its own injected provider_lookup rather than ever importing a
    concrete provider module itself."""

    def test_resolves_provider_via_lookup_callable(self):
        fake = FakeProvider(response_by_query={"acme": _outcome_with_one_result("Acme", "acme.example.com")})
        seen_keys = []

        def lookup(key):
            seen_keys.append(key)
            return fake

        service = SearchService(provider_lookup=lookup)
        outcome = service.discover("some_provider", _plan("acme"), context=None)
        self.assertEqual(seen_keys, ["some_provider"])
        self.assertEqual(len(outcome.results), 1)

    def test_unknown_provider_key_raises_keyerror_unchanged(self):
        def lookup(key):
            raise KeyError(f"Unknown discovery provider '{key}'")

        service = SearchService(provider_lookup=lookup)
        with self.assertRaises(KeyError):
            service.discover("nonexistent", _plan("q"), context=None)


class TestProviderInterfaceContract(unittest.TestCase):
    """'Provider interface' category - health() gates every discover()
    call before a single search() is attempted."""

    def test_disabled_provider_raises_without_calling_search(self):
        fake = FakeProvider(healthy=False)
        service = SearchService(provider_lookup=lambda key: fake)
        with self.assertRaises(ProviderError):
            service.discover("brave_search", _plan("q"), context=None)
        self.assertEqual(fake.calls, [], "an unhealthy/disabled provider must never have search() called on it")

    def test_empty_query_plan_short_circuits_without_calling_search(self):
        fake = FakeProvider()
        service = SearchService(provider_lookup=lambda key: fake)
        outcome = service.discover("brave_search", QueryPlan(variations=[]), context=None)
        self.assertEqual(outcome.results, [])
        self.assertEqual(outcome.request_count, 0)
        self.assertEqual(fake.calls, [])


class TestSuccessfulExecution(unittest.TestCase):
    def test_single_variation_success_merges_metrics(self):
        fake = FakeProvider(response_by_query={"cotton yarn": _outcome_with_one_result("Acme", "acme.example.com")})
        service = SearchService(provider_lookup=lambda key: fake)
        outcome = service.discover("brave_search", _plan("cotton yarn"), context=None)
        self.assertEqual(len(outcome.results), 1)
        self.assertEqual(outcome.results[0].name, "Acme")
        self.assertEqual(outcome.request_count, 1)
        self.assertAlmostEqual(outcome.api_cost, 0.002)

    def test_multiple_variations_for_one_provider_are_merged(self):
        fake = FakeProvider(
            response_by_query={
                "cotton yarn Germany": _outcome_with_one_result("Acme DE", "acme.de.example.com"),
                "cotton yarn France": _outcome_with_one_result("Acme FR", "acme.fr.example.com"),
            }
        )
        service = SearchService(provider_lookup=lambda key: fake)
        outcome = service.discover("brave_search", _plan("cotton yarn Germany", "cotton yarn France"), context=None)
        self.assertEqual(len(outcome.results), 2)
        self.assertEqual(outcome.request_count, 2)
        self.assertAlmostEqual(outcome.api_cost, 0.004)
        self.assertEqual(fake.calls, ["cotton yarn Germany", "cotton yarn France"])


class TestTimeoutHandling(unittest.TestCase):
    def test_a_timeout_on_one_variation_does_not_fail_the_others(self):
        fake = FakeProvider(
            response_by_query={
                "q1": ProviderTimeoutError("timed out"),
                "q2": _outcome_with_one_result("Acme", "acme.example.com"),
            }
        )
        service = SearchService(provider_lookup=lambda key: fake)
        outcome = service.discover("brave_search", _plan("q1", "q2"), context=None)
        self.assertEqual(len(outcome.results), 1)
        self.assertEqual(outcome.results[0].name, "Acme")

    def test_a_timeout_on_every_variation_raises_provider_error(self):
        fake = FakeProvider(default_error=ProviderTimeoutError("timed out"))
        service = SearchService(provider_lookup=lambda key: fake)
        with self.assertRaises(ProviderError):
            service.discover("brave_search", _plan("q1", "q2"), context=None)


class TestGenericExceptionHandling(unittest.TestCase):
    def test_a_generic_provider_error_on_one_variation_is_isolated(self):
        fake = FakeProvider(
            response_by_query={
                "q1": ProviderError("something went wrong"),
                "q2": _outcome_with_one_result("Acme", "acme.example.com"),
            }
        )
        service = SearchService(provider_lookup=lambda key: fake)
        outcome = service.discover("brave_search", _plan("q1", "q2"), context=None)
        self.assertEqual(len(outcome.results), 1)

    def test_a_non_provider_exception_is_not_swallowed(self):
        """SearchService only catches ProviderError - a genuine bug in a
        provider (e.g. an AttributeError) must surface, not be silently
        treated as graceful degradation."""
        fake = FakeProvider(default_error=RuntimeError("a real bug, not a provider failure"))
        service = SearchService(provider_lookup=lambda key: fake)
        with self.assertRaises(RuntimeError):
            service.discover("brave_search", _plan("q1"), context=None)


class TestMultipleProviders(unittest.TestCase):
    """'Multiple providers' category - SearchService itself is called
    once per provider_key (mirroring app.discovery.pipeline's own
    existing per-provider loop, unchanged by this phase - see that
    module's docstring), so 'multiple providers' is exercised by calling
    discover() more than once against different fakes, exactly as
    pipeline.py's real loop does."""

    def test_two_providers_produce_independent_outcomes(self):
        fake_a = FakeProvider(response_by_query={"q": _outcome_with_one_result("From A", "a.example.com")})
        fake_b = FakeProvider(response_by_query={"q": _outcome_with_one_result("From B", "b.example.com")})
        lookups = {"provider_a": fake_a, "provider_b": fake_b}
        service = SearchService(provider_lookup=lambda key: lookups[key])

        outcome_a = service.discover("provider_a", _plan("q"), context=None)
        outcome_b = service.discover("provider_b", _plan("q"), context=None)

        self.assertEqual(outcome_a.results[0].name, "From A")
        self.assertEqual(outcome_b.results[0].name, "From B")


class TestDuplicateResultsAcrossProviders(unittest.TestCase):
    """'Duplicate results across providers' category. SearchService
    itself is deliberately scoped to ONE provider per discover() call
    (see this module's own docstring and app.discovery.search_service's
    docstring) and does NOT dedup across separate discover() calls -
    that is, and remains, app.discovery.pipeline's own job, via
    app.discovery.identifier_lookup.find_duplicate_by_identifier() /
    app.discovery.dedup.find_duplicate(), which already runs uniformly
    over every provider's RawProviderResult output regardless of which
    provider_key produced it (see tests/test_discovery_dedup_pure.py -
    provider_key is not even an input to that matching logic). This test
    documents that SearchService's own contract is exactly "one
    provider's results, per call" - it would be a mistake to expect
    SearchService itself to silently drop a same-website candidate a
    second provider also found, since the existing, already-tested
    Prospect-level dedup tiers are what correctly collapse the two
    DiscoveryProviderResult rows into one Prospect later in the
    pipeline, with full audit trail (see pipeline.py's own
    'reseen_by_provider' timeline event) - collapsing them earlier, here,
    would destroy that audit trail."""

    def test_search_service_does_not_dedup_across_separate_provider_calls(self):
        fake_a = FakeProvider(response_by_query={"q": _outcome_with_one_result("Acme", "acme.example.com")})
        fake_b = FakeProvider(response_by_query={"q": _outcome_with_one_result("Acme Inc", "acme.example.com")})
        lookups = {"provider_a": fake_a, "provider_b": fake_b}
        service = SearchService(provider_lookup=lambda key: lookups[key])

        outcome_a = service.discover("provider_a", _plan("q"), context=None)
        outcome_b = service.discover("provider_b", _plan("q"), context=None)

        # Both calls independently surface the same website - SearchService
        # does not (and should not) collapse them; that is
        # app.discovery.pipeline's job, applied uniformly across BOTH
        # calls' combined output once they reach the per-provider loop.
        self.assertEqual(outcome_a.results[0].website, "acme.example.com")
        self.assertEqual(outcome_b.results[0].website, "acme.example.com")


class TestGracefulDegradation(unittest.TestCase):
    def test_some_variations_failing_still_returns_the_successful_ones(self):
        fake = FakeProvider(
            response_by_query={
                "q1": _outcome_with_one_result("Acme A", "a.example.com"),
                "q2": ProviderError("transient failure"),
                "q3": _outcome_with_one_result("Acme C", "c.example.com"),
            }
        )
        service = SearchService(provider_lookup=lambda key: fake)
        outcome = service.discover("brave_search", _plan("q1", "q2", "q3"), context=None)
        self.assertEqual({r.name for r in outcome.results}, {"Acme A", "Acme C"})
        self.assertEqual(outcome.request_count, 2)  # only the two successful variations contributed metrics


if __name__ == "__main__":
    unittest.main()
