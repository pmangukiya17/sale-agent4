"""
M11 (AI Provider Hierarchy) - E2E tests requiring Docker (sqlalchemy is not
imported here, but `app.core.config.settings` IS - constructing it needs
pydantic_settings, unavailable in the authoring sandbox - confirmed by
direct import attempt AND a direct `pip install pydantic-settings
--break-system-packages` attempt, both failing the same way every prior
milestone's own disclosure in this project already documents). Only
py_compile-checked in the authoring sandbox - run for real via
verify_m9_ai_provider_hierarchy.sh, in Docker.

Exercises AIGateway.complete()'s new premium-approval gate end to end,
using the SAME provider_lookup DI seam test_ai_execution_platform_e2e.py
already established (fake ProviderClients, no real anthropic/openai/
google.genai SDK calls) - only settings.AI_MODE /
settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL are read for real, via
monkeypatching the actual settings object for the duration of each test
(restored in tearDown - same discipline as every other test in this
project that temporarily mutates shared config/registries).

M-AIGW-1 (Provider-Neutral AI Gateway foundation) addition:
TestCapabilityAwareRouting below deliberately does NOT use the
ROUTING_POLICY test-only override (that bypasses capability-filtering
entirely by design - see router.py's own docstring) or a fake
provider_lookup for routing itself - it exercises ProviderRouter.select()
against the REAL PROVIDER_CLIENT_REGISTRY/CAPABILITY_PROVIDER_PREFERENCE
default list (["local_ollama", "groq", "claude"]) and each real client's
own declared _CAPABILITIES, which is why it needs Docker (importing the
real registry needs anthropic/openai/google.genai installed) even more
directly than the tests above. TestPreflight below DOES use the same fake
provider_lookup DI seam as the rest of this file, since preflight() only
calls `is_configured()` (never `complete()`) on whatever the DI seam
resolves.
"""
import unittest

from app.ai_gateway.client import AIGateway
from app.ai_gateway.errors import NoCapableProviderError, PremiumApprovalRequiredError
from app.ai_gateway.providers.base import ProviderClient
from app.ai_gateway.request import GatewayRequest, GatewayResponse, TokenUsage
from app.ai_gateway.router import ROUTING_POLICY, ProviderRouter, RoutingDecision
from app.core.config import settings


def _response(text: str, provider_key: str) -> GatewayResponse:
    return GatewayResponse(
        content=text,
        tool_calls=None,
        usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20, cost_usd=None),
        provider_key=provider_key,
        model="fake-model",
        finish_reason="stop",
    )


class _AlwaysUnavailableProviderClient(ProviderClient):
    key = "fake_local_down"

    def is_configured(self):
        return True

    def complete(self, request):
        from app.ai_gateway.errors import ProviderUnavailableError

        raise ProviderUnavailableError("simulated: local server not running", provider_key=self.key)


class _UnconfiguredProviderClient(ProviderClient):
    key = "fake_free_unconfigured"

    def is_configured(self):
        return False

    def complete(self, request):
        raise AssertionError("must never be called - is_configured() is False")


class _OkPremiumProviderClient(ProviderClient):
    key = "fake_premium_ok"

    def is_configured(self):
        return True

    def complete(self, request):
        return _response("premium response", provider_key=self.key)


def _make_gateway(clients: dict[str, ProviderClient]) -> AIGateway:
    def provider_lookup(key: str) -> ProviderClient:
        client = clients.get(key)
        if client is None:
            raise KeyError(key)
        return client

    return AIGateway(provider_lookup=provider_lookup)


class TestPremiumApprovalGate(unittest.TestCase):
    CAPABILITY = "test_m9_capability"

    def setUp(self):
        self._original_mode = settings.AI_MODE
        self._original_gate = settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL
        settings.AI_MODE = "hybrid_recommended"
        settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL = True
        ROUTING_POLICY[self.CAPABILITY] = RoutingDecision(
            primary="fake_local_down",
            fallbacks=["fake_free_unconfigured"],
            premium=["fake_premium_ok"],
        )

    def tearDown(self):
        settings.AI_MODE = self._original_mode
        settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL = self._original_gate
        ROUTING_POLICY.pop(self.CAPABILITY, None)

    def test_local_and_free_exhausted_raises_premium_approval_required(self):
        gateway = _make_gateway(
            {"fake_local_down": _AlwaysUnavailableProviderClient(), "fake_free_unconfigured": _UnconfiguredProviderClient()}
        )
        request = GatewayRequest(capability=self.CAPABILITY)

        with self.assertRaises(PremiumApprovalRequiredError) as ctx:
            gateway.complete(request)

        self.assertEqual(ctx.exception.candidate_provider_key, "fake_premium_ok")

    def test_premium_approved_true_proceeds_to_premium_provider(self):
        gateway = _make_gateway(
            {
                "fake_local_down": _AlwaysUnavailableProviderClient(),
                "fake_free_unconfigured": _UnconfiguredProviderClient(),
                "fake_premium_ok": _OkPremiumProviderClient(),
            }
        )
        request = GatewayRequest(capability=self.CAPABILITY, premium_approved=True)

        response = gateway.complete(request)

        self.assertEqual(response.provider_key, "fake_premium_ok")

    def test_gate_disabled_auto_attempts_premium_without_approval(self):
        settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL = False
        gateway = _make_gateway(
            {
                "fake_local_down": _AlwaysUnavailableProviderClient(),
                "fake_free_unconfigured": _UnconfiguredProviderClient(),
                "fake_premium_ok": _OkPremiumProviderClient(),
            }
        )
        request = GatewayRequest(capability=self.CAPABILITY, premium_approved=False)

        response = gateway.complete(request)

        self.assertEqual(response.provider_key, "fake_premium_ok")

    def test_local_only_mode_never_reaches_premium_even_when_approved(self):
        settings.AI_MODE = "local_only"
        # local_only mode is resolved by ProviderRouter.select() reading
        # CAPABILITY_PROVIDER_PREFERENCE, not this test's ROUTING_POLICY
        # override (which bypasses tiering entirely by design - see
        # router.py's own docstring) - remove the override for this one
        # test so the real tier-aware resolution actually runs.
        ROUTING_POLICY.pop(self.CAPABILITY, None)
        gateway = _make_gateway({"local_ollama": _AlwaysUnavailableProviderClient()})
        request = GatewayRequest(capability=self.CAPABILITY, premium_approved=True)

        with self.assertRaises(Exception) as ctx:
            gateway.complete(request)
        self.assertNotIsInstance(ctx.exception, PremiumApprovalRequiredError)


class TestCapabilityAwareRouting(unittest.TestCase):
    """M-AIGW-1. Real registry, real default CAPABILITY_PROVIDER_PREFERENCE
    (["local_ollama", "groq", "claude"]) - both local_ollama and groq
    declare reasoning_support=False (see openai_compatible_client.py's own
    _CAPABILITIES), claude declares reasoning_support=True (see
    claude_client.py's own _CAPABILITIES) - a real, disclosed-in-the-plan-
    doc fact about today's actual declarations, not a fake for this test."""

    CAPABILITY = "test_m_aigw_1_capability"

    def setUp(self):
        self._original_mode = settings.AI_MODE
        settings.AI_MODE = "hybrid_recommended"

    def tearDown(self):
        settings.AI_MODE = self._original_mode
        ROUTING_POLICY.pop(self.CAPABILITY, None)

    def test_requires_deep_reasoning_excludes_non_reasoning_providers(self):
        request = GatewayRequest(capability=self.CAPABILITY, requires_deep_reasoning=True)
        decision = ProviderRouter.select(request)
        # local_ollama/groq excluded (reasoning_support=False) - only
        # claude (reasoning_support=True) remains, and it's premium-tier,
        # so chain() is empty and premium carries it instead.
        self.assertEqual(decision.chain(), [])
        self.assertEqual(decision.premium, ["claude"])
        self.assertEqual(set(decision.capability_excluded), {"local_ollama", "groq"})

    def test_no_special_requirements_is_unaffected_by_capability_filtering(self):
        request = GatewayRequest(capability=self.CAPABILITY)
        decision = ProviderRouter.select(request)
        self.assertEqual(decision.chain(), ["local_ollama", "groq"])
        self.assertEqual(decision.premium, ["claude"])
        self.assertEqual(decision.capability_excluded, [])

    def test_no_capable_provider_at_all_raises_no_capable_provider_error(self):
        # local_only mode + requires_deep_reasoning=True: local_ollama is
        # the only chain candidate, and it lacks reasoning_support - chain
        # AND premium both end up empty specifically because of capability
        # exclusion (not because nothing was configured), which is exactly
        # the case NoCapableProviderError exists to distinguish from the
        # ordinary "no provider chain resolved" GatewayError.
        settings.AI_MODE = "local_only"
        gateway = AIGateway(provider_lookup=lambda key: (_ for _ in ()).throw(AssertionError("must never be resolved")))
        request = GatewayRequest(capability=self.CAPABILITY, requires_deep_reasoning=True)

        with self.assertRaises(NoCapableProviderError) as ctx:
            gateway.complete(request)
        self.assertIn("local_ollama", ctx.exception.excluded_provider_keys)


class TestPreflight(unittest.TestCase):
    """M-AIGW-1. AIGateway.preflight() - the same fake provider_lookup DI
    seam as TestPremiumApprovalGate above (preflight() only ever calls
    is_configured(), never complete(), so no real SDK call risk either
    way)."""

    CAPABILITY = "test_m_aigw_1_preflight_capability"

    def setUp(self):
        self._original_mode = settings.AI_MODE
        self._original_gate = settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL
        settings.AI_MODE = "hybrid_recommended"
        settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL = True
        ROUTING_POLICY[self.CAPABILITY] = RoutingDecision(
            primary="fake_local_down", fallbacks=["fake_free_unconfigured"], premium=["fake_premium_ok"]
        )

    def tearDown(self):
        settings.AI_MODE = self._original_mode
        settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL = self._original_gate
        ROUTING_POLICY.pop(self.CAPABILITY, None)

    def test_configured_candidate_in_chain_means_no_approval_needed(self):
        gateway = _make_gateway({"fake_local_down": _OkPremiumProviderClient()})
        # _OkPremiumProviderClient.is_configured() -> True, so this counts
        # as "chain has a configured candidate" even though its key isn't
        # semantically "local" - preflight() only checks is_configured(),
        # exactly like the in-flight walk does.
        result = gateway.preflight(GatewayRequest(capability=self.CAPABILITY))
        self.assertFalse(result.approval_required)

    def test_nothing_configured_in_chain_reports_approval_required_with_estimate(self):
        gateway = _make_gateway(
            {"fake_local_down": _AlwaysUnavailableProviderClient(), "fake_free_unconfigured": _UnconfiguredProviderClient()}
        )
        result = gateway.preflight(GatewayRequest(capability=self.CAPABILITY), prompt_char_length=5_000)
        self.assertTrue(result.approval_required)
        self.assertEqual(result.candidate_provider_key, "fake_premium_ok")

    def test_gate_disabled_means_no_approval_needed(self):
        settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL = False
        gateway = _make_gateway(
            {"fake_local_down": _AlwaysUnavailableProviderClient(), "fake_free_unconfigured": _UnconfiguredProviderClient()}
        )
        result = gateway.preflight(GatewayRequest(capability=self.CAPABILITY))
        self.assertFalse(result.approval_required)


if __name__ == "__main__":
    unittest.main()
