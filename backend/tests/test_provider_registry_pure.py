"""
tests.test_provider_registry_pure - M2 Phase 2.

app.discovery.providers.registry ITSELF imports cleanly with zero
third-party dependency (lazy-import design - see that module's own
docstring), and is exercised for real below. Actually INSTANTIATING a
provider via get_provider() still requires that provider's own real
dependency (sqlalchemy, transitively, for manual_csv - see
manual_csv.py's own pre-existing `from app.discovery.context import
DiscoveryContext`, unchanged by this phase; httpx for brave_search) -
this was already true before Phase 2 and is unrelated to the lazy-import
fix, which only changes WHEN that dependency is required (at
instantiation time, not at "merely importing registry.py" time), never
WHETHER it's required at all. This project's authoring sandbox has
neither sqlalchemy nor httpx installed (no PyPI access - a disclosed,
standing constraint), so the tests below that actually call
get_provider() are written to pass in EITHER environment: this sandbox
(where instantiation fails with an ImportError for a missing dependency)
and a real Docker environment with both installed (where it succeeds) -
see each test's own comment for how.

Run standalone with:
    python -m unittest tests.test_provider_registry_pure
"""
import unittest

from app.discovery.providers.registry import (
    DIRECT_PROVIDER_KEYS,
    SEARCH_PROVIDER_KEYS,
    get_provider,
    is_search_provider,
    iter_enabled_providers,
)


class TestProviderClassification(unittest.TestCase):
    """Pure data - no instantiation, no dependency needed at all."""

    def test_manual_csv_is_direct_not_search(self):
        self.assertIn("manual_csv", DIRECT_PROVIDER_KEYS)
        self.assertNotIn("manual_csv", SEARCH_PROVIDER_KEYS)
        self.assertFalse(is_search_provider("manual_csv"))

    def test_brave_search_is_search_not_direct(self):
        self.assertIn("brave_search", SEARCH_PROVIDER_KEYS)
        self.assertNotIn("brave_search", DIRECT_PROVIDER_KEYS)
        self.assertTrue(is_search_provider("brave_search"))

    def test_unknown_key_is_not_a_search_provider(self):
        # is_search_provider() is a routing decision only - it never
        # raises for an unknown key (see its own docstring); get_provider()
        # below is what validates existence.
        self.assertFalse(is_search_provider("totally_unknown_key"))

    def test_direct_and_search_keys_never_overlap(self):
        self.assertEqual(DIRECT_PROVIDER_KEYS & SEARCH_PROVIDER_KEYS, frozenset())


class TestGetProviderUnknownKey(unittest.TestCase):
    """This path never attempts an import (the dict lookup fails first),
    so it's genuinely dependency-free and passes identically in every
    environment."""

    def test_unknown_provider_key_raises_keyerror_with_a_helpful_message(self):
        with self.assertRaises(KeyError) as ctx:
            get_provider("totally_unknown_key")
        self.assertIn("Unknown discovery provider", str(ctx.exception))
        self.assertIn("manual_csv", str(ctx.exception))
        self.assertIn("brave_search", str(ctx.exception))


class TestGetProviderKnownKeys(unittest.TestCase):
    """Actually instantiating a real provider needs that provider's own
    dependency installed - see this module's own docstring. Written to
    pass in both this sandbox (dependency missing -> ImportError) and a
    real Docker environment (dependency installed -> a working
    provider instance) without weakening what's actually asserted in
    either case."""

    def _assert_resolves_or_discloses_missing_dependency(self, provider_key: str, expected_class_name: str):
        try:
            provider = get_provider(provider_key)
        except ImportError as exc:
            # Expected in this authoring sandbox (no PyPI access) -
            # confirms get_provider() at least got PAST the dict lookup
            # and attempted the real lazy import, which is exactly what
            # should happen for a known key.
            self.skipTest(f"{provider_key}'s own dependency is not installed in this sandbox: {exc}")
        else:
            self.assertEqual(type(provider).__name__, expected_class_name)
            self.assertEqual(provider.key, provider_key)

    def test_manual_csv_resolves_to_the_real_class(self):
        self._assert_resolves_or_discloses_missing_dependency("manual_csv", "ManualCSVProvider")

    def test_brave_search_resolves_to_the_real_class(self):
        self._assert_resolves_or_discloses_missing_dependency("brave_search", "BraveSearchProvider")


class TestIterEnabledProviders(unittest.TestCase):
    def test_never_raises_and_returns_a_list(self):
        # In this sandbox both providers' own instantiation fails
        # (missing sqlalchemy/httpx respectively), so this legitimately
        # returns [] here - iter_enabled_providers()'s own broad except
        # is precisely what keeps that a graceful [] instead of a crash
        # (see its own docstring). In a real Docker environment with
        # BRAVE_SEARCH_API_KEY unset, manual_csv would appear (health()
        # defaults True) and brave_search would not (health() False).
        result = iter_enabled_providers()
        self.assertIsInstance(result, list)
        for key in result:
            self.assertIn(key, DIRECT_PROVIDER_KEYS | SEARCH_PROVIDER_KEYS)


if __name__ == "__main__":
    unittest.main()
