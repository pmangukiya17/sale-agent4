"""
M8.3 (AI Gateway Management & Control, Step 2 - Provider Management) -
pure, zero-third-party-dependency tests. Genuinely executable in the
authoring sandbox (no Docker, no pydantic/pydantic_settings, no
sqlalchemy, no anthropic/openai/google-genai SDKs - see
tests/test_provider_config_pure.py's own disclosure for this project's
standing sandbox constraint).

Covers exactly the one module this milestone's Step 2 touches that has
NO impure imports at all: app.ai_gateway.providers.base - specifically
`ConnectionTestResult` and `ProviderClient.test_connection()`'s own
default implementation. Every concrete client's own `test_connection()`
override (claude_client.py/openai_client.py/gemini_client.py/
openai_compatible_client.py) is NOT covered here - each of those modules
`import anthropic`/`import openai`/`import google.genai` at module level,
so importing them at all requires those SDKs to be installed (they are
not, in this sandbox) - see test_provider_management_e2e.py's own
disclosure for that coverage instead.

Run standalone with:
    python -m unittest tests.test_ai_gateway_provider_management_pure
"""
import unittest

from app.ai_gateway.providers.base import ConnectionTestResult, ProviderClient
from app.ai_gateway.request import GatewayRequest, GatewayResponse


class _NotConfiguredFakeClient(ProviderClient):
    key = "fake_not_configured"

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        raise NotImplementedError

    def is_configured(self) -> bool:
        return False


class _ConfiguredButNoOverrideFakeClient(ProviderClient):
    """A fake client that is 'configured' but predates this milestone -
    exactly the backward-compatibility scenario base.py's own docstring
    describes (a test-only fake that only implements key/is_configured/
    complete)."""

    key = "fake_configured_no_override"

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        raise NotImplementedError

    def is_configured(self) -> bool:
        return True


class TestConnectionTestResult(unittest.TestCase):
    def test_defaults(self):
        result = ConnectionTestResult(success=True, message="Connected")
        self.assertTrue(result.success)
        self.assertEqual(result.message, "Connected")
        self.assertIsNone(result.latency_ms)
        self.assertIsNone(result.available_models)

    def test_is_frozen(self):
        result = ConnectionTestResult(success=True, message="Connected")
        with self.assertRaises(Exception):
            result.success = False  # type: ignore[misc]


class TestProviderClientTestConnectionDefault(unittest.TestCase):
    def test_not_configured_reports_failure_without_raising(self):
        client = _NotConfiguredFakeClient()
        result = client.test_connection()
        self.assertFalse(result.success)
        self.assertIn("not configured", result.message)
        self.assertIsNone(result.latency_ms)
        self.assertIsNone(result.available_models)

    def test_configured_but_no_override_raises_not_implemented(self):
        client = _ConfiguredButNoOverrideFakeClient()
        with self.assertRaises(NotImplementedError):
            client.test_connection()


if __name__ == "__main__":
    unittest.main()
