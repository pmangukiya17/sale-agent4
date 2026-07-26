"""
M-AIGW-1 (Provider-Neutral AI Gateway foundation) - pure, zero-third-party-
dependency tests, genuinely executable in this project's authoring sandbox
(no Docker, no pydantic_settings, no sqlalchemy - same disclosed convention
as tests/test_ai_provider_hierarchy_pure.py). Covers
app.ai_gateway.capabilities in full, plus
app.ai_gateway.router._apply_capability_filter - importable and callable
without settings because it takes an already-built RoutingDecision and a
GatewayRequest, never touching ProviderRouter.select() itself (which is
the one function in router.py that needs settings, lazily imported inside
itself, unchanged by this milestone).

NOT covered here (needs Docker - see test_ai_provider_hierarchy_e2e.py's
own disclosure): ProviderRouter.select()'s lazy PROVIDER_CLIENT_REGISTRY
import, AIGateway.complete()'s NoCapableProviderError raise end to end,
AIGateway.preflight() end to end (both read settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL).
"""
import unittest

from app.ai_gateway.capabilities import (
    ProviderCapabilities,
    RequiredCapabilities,
    derive_required_capabilities,
    filter_capable,
    register_capability_override,
    resolve_capabilities,
    satisfies,
)
from app.ai_gateway.request import GatewayRequest, ResponseFormat, ResponseFormatType, ToolSpec
from app.ai_gateway.router import RoutingDecision, _apply_capability_filter


class TestDeriveRequiredCapabilities(unittest.TestCase):
    def test_plain_request_requires_nothing(self):
        request = GatewayRequest(capability="x")
        required = derive_required_capabilities(request)
        self.assertFalse(required.any_required())

    def test_json_response_format_requires_structured_output(self):
        request = GatewayRequest(capability="x", response_format=ResponseFormat(type=ResponseFormatType.JSON))
        required = derive_required_capabilities(request)
        self.assertTrue(required.structured_output)
        self.assertTrue(required.any_required())

    def test_text_response_format_does_not_require_structured_output(self):
        request = GatewayRequest(capability="x", response_format=ResponseFormat(type=ResponseFormatType.TEXT))
        required = derive_required_capabilities(request)
        self.assertFalse(required.structured_output)

    def test_tools_requires_tool_calling(self):
        request = GatewayRequest(
            capability="x", tools=[ToolSpec(name="lookup", description="d", parameters_json_schema={})]
        )
        required = derive_required_capabilities(request)
        self.assertTrue(required.tool_calling)

    def test_requires_deep_reasoning_requires_reasoning_support(self):
        request = GatewayRequest(capability="x", requires_deep_reasoning=True)
        required = derive_required_capabilities(request)
        self.assertTrue(required.reasoning_support)


class TestSatisfies(unittest.TestCase):
    def test_capable_provider_satisfies_everything_required(self):
        caps = ProviderCapabilities(structured_output=True, tool_calling=True, reasoning_support=True)
        required = RequiredCapabilities(structured_output=True, tool_calling=True, reasoning_support=True)
        self.assertTrue(satisfies(caps, required))

    def test_missing_one_capability_fails(self):
        caps = ProviderCapabilities(structured_output=True, tool_calling=False)
        required = RequiredCapabilities(structured_output=True, tool_calling=True)
        self.assertFalse(satisfies(caps, required))

    def test_nothing_required_always_satisfied(self):
        caps = ProviderCapabilities()  # all-conservative default
        self.assertTrue(satisfies(caps, RequiredCapabilities()))


class TestResolveCapabilities(unittest.TestCase):
    def test_unknown_provider_key_resolves_to_conservative_default(self):
        resolved = resolve_capabilities("nobody_declared_this", None, provider_level={})
        self.assertEqual(resolved, ProviderCapabilities())

    def test_model_none_returns_provider_level_only(self):
        provider_level = {"claude": ProviderCapabilities(structured_output=True, max_context_tokens=200_000)}
        resolved = resolve_capabilities("claude", None, provider_level=provider_level)
        self.assertEqual(resolved.max_context_tokens, 200_000)

    def test_model_override_merges_on_top_of_provider_level(self):
        provider_level = {"claude": ProviderCapabilities(structured_output=True, reasoning_support=False)}
        register_capability_override("claude", "claude-test-reasoning-model", reasoning_support=True, max_context_tokens=1_000_000)
        resolved = resolve_capabilities("claude", "claude-test-reasoning-model", provider_level=provider_level)
        self.assertTrue(resolved.reasoning_support)
        self.assertEqual(resolved.max_context_tokens, 1_000_000)
        self.assertTrue(resolved.structured_output)  # inherited from provider-level, not overridden

    def test_model_with_no_override_falls_back_to_provider_level(self):
        provider_level = {"claude": ProviderCapabilities(structured_output=True)}
        resolved = resolve_capabilities("claude", "some-other-model-with-no-override", provider_level=provider_level)
        self.assertEqual(resolved, provider_level["claude"])


class TestFilterCapable(unittest.TestCase):
    def test_nothing_required_returns_input_unchanged_no_excluded(self):
        capable, excluded = filter_capable(
            ["a", "b", "c"], RequiredCapabilities(), model=None, provider_level={}
        )
        self.assertEqual(capable, ["a", "b", "c"])
        self.assertEqual(excluded, [])

    def test_filters_out_incapable_providers_preserving_order(self):
        provider_level = {
            "capable_one": ProviderCapabilities(tool_calling=True),
            "incapable": ProviderCapabilities(tool_calling=False),
            "capable_two": ProviderCapabilities(tool_calling=True),
        }
        capable, excluded = filter_capable(
            ["capable_one", "incapable", "capable_two"],
            RequiredCapabilities(tool_calling=True),
            model=None,
            provider_level=provider_level,
        )
        self.assertEqual(capable, ["capable_one", "capable_two"])
        self.assertEqual(excluded, ["incapable"])

    def test_unregistered_provider_key_is_excluded_when_something_is_required(self):
        capable, excluded = filter_capable(
            ["nobody_declared_this"], RequiredCapabilities(structured_output=True), model=None, provider_level={}
        )
        self.assertEqual(capable, [])
        self.assertEqual(excluded, ["nobody_declared_this"])


class TestApplyCapabilityFilterInRouter(unittest.TestCase):
    """Exercises router._apply_capability_filter directly - the function
    ProviderRouter.select() calls after _build_decision() - fully pure
    (provider_level is an explicit parameter here, never resolved by this
    function itself - see its own docstring), so no settings/
    PROVIDER_CLIENT_REGISTRY import is ever triggered by these tests."""

    def test_no_requirements_returns_decision_unchanged(self):
        decision = RoutingDecision(primary="local_ollama", fallbacks=["groq"], premium=["claude"])
        request = GatewayRequest(capability="x")
        result = _apply_capability_filter(decision, request, provider_level={})
        self.assertEqual(result.chain(), ["local_ollama", "groq"])
        self.assertEqual(result.premium, ["claude"])
        self.assertEqual(result.capability_excluded, [])

    def test_requirement_with_no_provider_level_data_excludes_everything(self):
        # An empty provider_level means no provider has any declared
        # capability, so a real requirement excludes every candidate - the
        # fail-safe direction (see capabilities.resolve_capabilities's own
        # docstring for why an unregistered provider_key defaults to the
        # all-conservative ProviderCapabilities()).
        decision = RoutingDecision(primary="local_ollama", fallbacks=["groq"], premium=["claude"])
        request = GatewayRequest(capability="x", response_format=ResponseFormat(type=ResponseFormatType.JSON))
        result = _apply_capability_filter(decision, request, provider_level={})
        self.assertEqual(result.chain(), [])
        self.assertEqual(result.premium, [])
        self.assertEqual(set(result.capability_excluded), {"local_ollama", "groq", "claude"})

    def test_realistic_provider_level_lets_capable_candidates_through(self):
        # Mirrors what select() would actually build from
        # PROVIDER_CLIENT_REGISTRY today: every real provider declares
        # structured_output=True (see each client's own _CAPABILITIES) -
        # confirming a JSON-schema request (Research's own real traffic
        # shape) passes through capability-filtering unchanged in practice.
        provider_level = {
            "local_ollama": ProviderCapabilities(structured_output=True, tool_calling=True),
            "groq": ProviderCapabilities(structured_output=True, tool_calling=True),
            "claude": ProviderCapabilities(structured_output=True, tool_calling=True, reasoning_support=True),
        }
        decision = RoutingDecision(primary="local_ollama", fallbacks=["groq"], premium=["claude"])
        request = GatewayRequest(capability="x", response_format=ResponseFormat(type=ResponseFormatType.JSON))
        result = _apply_capability_filter(decision, request, provider_level=provider_level)
        self.assertEqual(result.chain(), ["local_ollama", "groq"])
        self.assertEqual(result.premium, ["claude"])
        self.assertEqual(result.capability_excluded, [])


if __name__ == "__main__":
    unittest.main()
