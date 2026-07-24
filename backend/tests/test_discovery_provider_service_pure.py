"""
tests.test_discovery_provider_service_pure - M2 Phase 2 UX follow-up.

Genuinely executed in this sandbox: app.discovery.provider_service
imports cleanly with zero third-party dependency (registry.py's own
lazy-import design already established this - see that module's
docstring; provider_service.py adds nothing beyond stdlib
dataclasses/typing on top of it). Deterministic cases below patch
`app.discovery.provider_service.get_provider` directly (a normal
testing technique, not a production-code change - DiscoveryProviderService
itself gains no dependency-injection seam, per the CEO's own "no
unnecessary backend complexity" instruction) so these tests don't
depend on whether sqlalchemy/httpx happen to be installed in whatever
environment runs them.

The route itself (app/api/routes/discovery_providers.py) is NOT tested
here - it needs a real `User` instance, which transitively requires
sqlalchemy just to import the model, and this project's authoring
sandbox has no sqlalchemy install. See
tests/test_discovery_providers_route.py for that DB-backed,
disclosed-unrunnable-here coverage.

Run standalone with:
    python -m unittest tests.test_discovery_provider_service_pure
"""
import unittest
from unittest.mock import patch

from app.discovery.provider_service import DiscoveryProviderInfo, DiscoveryProviderService
from app.discovery.providers.base import DiscoveryProvider, ProviderSearchOutcome


class FakeProvider(DiscoveryProvider):
    """Duck-typed stand-in - only needs to satisfy the three methods
    DiscoveryProviderService.list_providers() actually calls."""

    key = "fake"

    def __init__(self, *, name: str = "Fake Provider", healthy: bool = True, capabilities: dict | None = None):
        self._name = name
        self._healthy = healthy
        self._capabilities = capabilities or {}

    def provider_name(self) -> str:
        return self._name

    def health(self) -> bool:
        return self._healthy

    def capabilities(self) -> dict:
        return self._capabilities

    def search(self, query_spec, context) -> ProviderSearchOutcome:  # pragma: no cover - unused here
        raise NotImplementedError


class TestDiscoveryProviderServiceListProviders(unittest.TestCase):
    def test_real_registered_keys_are_iterated(self):
        # Uses the REAL list_registered_provider_keys() (dependency-free)
        # but patches get_provider so construction never actually needs
        # sqlalchemy/httpx - deterministic regardless of environment.
        with patch("app.discovery.provider_service.get_provider", return_value=FakeProvider()):
            result = DiscoveryProviderService().list_providers()
        keys = {info.key for info in result}
        self.assertEqual(keys, {"manual_csv", "brave_search"})

    def test_healthy_provider_reports_enabled_true_with_real_name(self):
        fake = FakeProvider(name="Manual / CSV Import", healthy=True, capabilities={"query_driven": False})
        with patch("app.discovery.provider_service.get_provider", return_value=fake):
            result = DiscoveryProviderService().list_providers()
        for info in result:
            self.assertTrue(info.enabled)
            self.assertEqual(info.name, "Manual / CSV Import")
            self.assertEqual(info.capabilities, {"query_driven": False})

    def test_unhealthy_provider_reports_enabled_false_but_keeps_real_name(self):
        fake = FakeProvider(name="Brave Search", healthy=False)
        with patch("app.discovery.provider_service.get_provider", return_value=fake):
            result = DiscoveryProviderService().list_providers()
        for info in result:
            self.assertFalse(info.enabled)
            self.assertEqual(info.name, "Brave Search")

    def test_a_provider_that_fails_to_construct_degrades_to_disabled_not_an_exception(self):
        def _raise(key):
            raise ImportError(f"No module named 'httpx' (simulating {key})")

        with patch("app.discovery.provider_service.get_provider", side_effect=_raise):
            result = DiscoveryProviderService().list_providers()  # must not raise

        self.assertEqual(len(result), 2)
        for info in result:
            self.assertFalse(info.enabled)
            self.assertEqual(info.name, info.key)  # falls back to the raw key
            self.assertEqual(info.capabilities, {})

    def test_returns_the_documented_dataclass_shape(self):
        with patch("app.discovery.provider_service.get_provider", return_value=FakeProvider()):
            result = DiscoveryProviderService().list_providers()
        for info in result:
            self.assertIsInstance(info, DiscoveryProviderInfo)


class TestDiscoveryProviderServiceRealEnvironment(unittest.TestCase):
    """No mocking - exercises the real registry.get_provider() path.
    Assertions are deliberately environment-tolerant (this sandbox has
    neither sqlalchemy nor httpx installed, so both real providers are
    expected to degrade to enabled=False here; a real Docker environment
    with both installed - and BRAVE_SEARCH_API_KEY unset - would show
    manual_csv enabled=True, brave_search enabled=False). The one thing
    asserted unconditionally is the contract that matters everywhere:
    this never raises, and always returns exactly the registered keys."""

    def test_never_raises_and_returns_every_registered_key(self):
        result = DiscoveryProviderService().list_providers()
        self.assertEqual({info.key for info in result}, {"manual_csv", "brave_search"})
        for info in result:
            self.assertIsInstance(info.enabled, bool)
            self.assertIsInstance(info.name, str)
            self.assertIsInstance(info.capabilities, dict)


if __name__ == "__main__":
    unittest.main()
