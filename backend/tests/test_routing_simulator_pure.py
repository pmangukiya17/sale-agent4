"""
M8.3 (AI Gateway Management & Control, Step 4 - Routing Simulator) - pure,
zero-third-party-dependency tests for
`app.ai_gateway.routing_simulator.build_simulation()`. Genuinely
executable in this project's authoring sandbox (no pydantic_settings, no
sqlalchemy - same disclosed convention as
tests/test_ai_provider_hierarchy_pure.py/tests/test_ai_gateway_capabilities_pure.py)
since `routing_simulator.py` never imports `app.core.config.settings` or
sqlalchemy at module level - every "impure" fact (is_configured, prices,
the premium-approval gate setting) is supplied here via a plain fake
callable/value, exactly the DI seam `build_simulation()`'s own docstring
describes.

NOT covered here (needs settings/PROVIDER_CLIENT_REGISTRY - belongs in an
e2e-shaped test instead, not written this pass since
`ui_query.simulate_routing()` is a thin, already-covered-by-construction
wiring layer over this module's own pure logic plus
`router._build_decision()`/`capabilities.derive_required_capabilities()`,
both independently pure-tested already): the real
`ui_query.simulate_routing()` glue function and the
`POST /ai-gateway/routing/simulate` route's request validation.
"""
import unittest

from app.ai_gateway.capabilities import ProviderCapabilities, RequiredCapabilities
from app.ai_gateway.router import RoutingDecision
from app.ai_gateway.routing_simulator import build_simulation

_ALL_CAPABLE = ProviderCapabilities(structured_output=True, tool_calling=True, reasoning_support=True)
_NO_STRUCTURED_OUTPUT = ProviderCapabilities(structured_output=False, tool_calling=True, reasoning_support=True)


def _tier_of(key: str) -> str:
    return {"local_ollama": "local", "groq": "free", "gemini_ai_studio": "free", "claude": "premium"}.get(key, "premium")


def _label_of(key: str) -> str:
    return {"local_ollama": "Ollama", "groq": "Groq", "gemini_ai_studio": "Gemini AI Studio", "claude": "Claude"}.get(key, key)


def _price_of(key: str):
    return {"claude": (0.003, 0.015)}.get(key, (0.0, 0.0))


def _no_required() -> RequiredCapabilities:
    return RequiredCapabilities()


class TestBuildSimulationBasicChain(unittest.TestCase):
    def test_primary_configured_is_would_call_fallback_is_not_reached(self):
        decision = RoutingDecision(primary="local_ollama", fallbacks=["groq"])
        result = build_simulation(
            decision,
            _no_required(),
            provider_level={},
            is_configured=lambda key: key == "local_ollama",
            require_premium_approval=True,
            tier_of=_tier_of,
            label_of=_label_of,
            price_of=_price_of,
            estimate_cost=lambda key: None,
        )
        self.assertEqual(result.outcome, "success")
        self.assertEqual([n.state for n in result.nodes], ["would_call", "skipped_not_reached"])
        self.assertEqual(result.nodes[0].role, "primary")
        self.assertEqual(result.nodes[0].position, 0)
        self.assertEqual(result.nodes[1].role, "fallback")
        self.assertEqual(result.nodes[1].position, 1)

    def test_primary_not_configured_falls_through_to_fallback(self):
        decision = RoutingDecision(primary="local_ollama", fallbacks=["groq"])
        result = build_simulation(
            decision,
            _no_required(),
            provider_level={},
            is_configured=lambda key: key == "groq",
            require_premium_approval=True,
            tier_of=_tier_of,
            label_of=_label_of,
            price_of=_price_of,
            estimate_cost=lambda key: None,
        )
        self.assertEqual(result.outcome, "success")
        self.assertEqual([n.state for n in result.nodes], ["skipped_not_configured", "would_call"])

    def test_nothing_configured_no_premium_outcome_is_failed(self):
        decision = RoutingDecision(primary="local_ollama", fallbacks=["groq"])
        result = build_simulation(
            decision,
            _no_required(),
            provider_level={},
            is_configured=lambda key: False,
            require_premium_approval=True,
            tier_of=_tier_of,
            label_of=_label_of,
            price_of=_price_of,
            estimate_cost=lambda key: None,
        )
        self.assertEqual(result.outcome, "failed")
        self.assertTrue(all(n.state == "skipped_not_configured" for n in result.nodes))


class TestBuildSimulationPremium(unittest.TestCase):
    def test_premium_gated_behind_approval_when_chain_exhausted(self):
        decision = RoutingDecision(primary="local_ollama", fallbacks=[], premium=["claude"])
        result = build_simulation(
            decision,
            _no_required(),
            provider_level={},
            is_configured=lambda key: key == "claude",
            require_premium_approval=True,
            tier_of=_tier_of,
            label_of=_label_of,
            price_of=_price_of,
            estimate_cost=lambda key: 0.05 if key == "claude" else None,
        )
        self.assertEqual(result.outcome, "waiting")
        premium_node = result.nodes[-1]
        self.assertEqual(premium_node.role, "premium")
        self.assertEqual(premium_node.state, "requires_approval")
        self.assertEqual(premium_node.estimated_cost_usd, 0.05)

    def test_premium_auto_used_when_approval_gate_disabled(self):
        decision = RoutingDecision(primary="local_ollama", fallbacks=[], premium=["claude"])
        result = build_simulation(
            decision,
            _no_required(),
            provider_level={},
            is_configured=lambda key: key == "claude",
            require_premium_approval=False,
            tier_of=_tier_of,
            label_of=_label_of,
            price_of=_price_of,
            estimate_cost=lambda key: 0.05,
        )
        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.nodes[-1].state, "would_call")

    def test_premium_not_configured_stays_failed(self):
        decision = RoutingDecision(primary=None, fallbacks=[], premium=["claude"])
        result = build_simulation(
            decision,
            _no_required(),
            provider_level={},
            is_configured=lambda key: False,
            require_premium_approval=True,
            tier_of=_tier_of,
            label_of=_label_of,
            price_of=_price_of,
            estimate_cost=lambda key: None,
        )
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.nodes[-1].state, "skipped_not_configured")


class TestBuildSimulationOverrides(unittest.TestCase):
    def test_override_makes_a_really_unconfigured_provider_would_call(self):
        decision = RoutingDecision(primary="groq", fallbacks=[])
        result = build_simulation(
            decision,
            _no_required(),
            provider_level={},
            is_configured=lambda key: False,  # really NOT configured
            overrides={"groq": True},  # simulated as if it were
            require_premium_approval=True,
            tier_of=_tier_of,
            label_of=_label_of,
            price_of=_price_of,
            estimate_cost=lambda key: None,
        )
        node = result.nodes[0]
        self.assertEqual(node.state, "would_call")
        self.assertTrue(node.overridden)
        self.assertFalse(node.configured)  # real fact preserved, distinct from the simulated state

    def test_override_makes_a_really_configured_provider_skip(self):
        decision = RoutingDecision(primary="groq", fallbacks=["claude"], premium=[])
        result = build_simulation(
            decision,
            _no_required(),
            provider_level={},
            is_configured=lambda key: True,  # really configured
            overrides={"groq": False},  # simulated as disabled
            require_premium_approval=True,
            tier_of=_tier_of,
            label_of=_label_of,
            price_of=_price_of,
            estimate_cost=lambda key: None,
        )
        self.assertEqual(result.nodes[0].state, "skipped_not_configured")
        self.assertTrue(result.nodes[0].overridden)
        self.assertTrue(result.nodes[0].configured)
        self.assertEqual(result.nodes[1].state, "would_call")

    def test_provider_absent_from_overrides_is_unaffected(self):
        decision = RoutingDecision(primary="groq", fallbacks=[])
        result = build_simulation(
            decision,
            _no_required(),
            provider_level={},
            is_configured=lambda key: True,
            overrides={"claude": False},  # irrelevant key
            require_premium_approval=True,
            tier_of=_tier_of,
            label_of=_label_of,
            price_of=_price_of,
            estimate_cost=lambda key: None,
        )
        self.assertEqual(result.nodes[0].state, "would_call")
        self.assertFalse(result.nodes[0].overridden)


class TestBuildSimulationCapabilityFilter(unittest.TestCase):
    def test_capability_mismatch_is_skipped_with_a_reason_and_reported_excluded(self):
        decision = RoutingDecision(primary="groq", fallbacks=["claude"])
        required = RequiredCapabilities(structured_output=True)
        result = build_simulation(
            decision,
            required,
            provider_level={"groq": _NO_STRUCTURED_OUTPUT, "claude": _ALL_CAPABLE},
            is_configured=lambda key: True,
            require_premium_approval=True,
            tier_of=_tier_of,
            label_of=_label_of,
            price_of=_price_of,
            estimate_cost=lambda key: None,
        )
        self.assertEqual(result.nodes[0].state, "skipped_capability_mismatch")
        self.assertIn("structured output", result.nodes[0].reason)
        self.assertEqual(result.nodes[1].state, "would_call")
        self.assertEqual(result.capability_excluded, ["groq"])

    def test_no_requirements_never_excludes_anything(self):
        decision = RoutingDecision(primary="groq", fallbacks=["claude"])
        result = build_simulation(
            decision,
            RequiredCapabilities(),  # nothing required
            provider_level={"groq": _NO_STRUCTURED_OUTPUT, "claude": _ALL_CAPABLE},
            is_configured=lambda key: True,
            require_premium_approval=True,
            tier_of=_tier_of,
            label_of=_label_of,
            price_of=_price_of,
            estimate_cost=lambda key: None,
        )
        self.assertEqual(result.capability_excluded, [])
        self.assertEqual(result.nodes[0].state, "would_call")


if __name__ == "__main__":
    unittest.main()
