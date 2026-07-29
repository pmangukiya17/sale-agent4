"""
M8.3 (AI Gateway Management & Control, Step 6 - Gateway Diagnostics) -
pure, zero-third-party-dependency tests for
`app.ai_gateway.diagnostics.build_diagnostics()`. Genuinely executable in
this project's authoring sandbox (no pydantic_settings, no sqlalchemy -
same disclosed convention as tests/test_routing_simulator_pure.py/
tests/test_ai_gateway_capabilities_pure.py) since `diagnostics.py` never
imports `app.core.config.settings` or sqlalchemy at module level - every
input (provider health, routing outcomes, recent failures) is a plain
dataclass instance constructed directly by these tests, exactly the shape
`ui_query.get_diagnostics()` itself builds from real telemetry.

NOT covered here (needs settings/sqlalchemy - belongs in an e2e-shaped
test instead): the real `ui_query.get_diagnostics()` glue function
(providers_input construction via get_provider_config()/is_configured(),
the grouped AIRequestLog query, and the GET /ai-gateway/diagnostics route
itself, including its admin gate).
"""
import unittest

from app.ai_gateway.diagnostics import (
    FailureSummaryInput,
    ProviderHealthInput,
    RoutingOutcomeInput,
    build_diagnostics,
)


def _healthy_provider(key: str, tier: str = "local") -> ProviderHealthInput:
    return ProviderHealthInput(provider_key=key, label=key.title(), tier=tier, enabled=True, configured=True)


class TestProviderHealthFindings(unittest.TestCase):
    def test_all_healthy_providers_produce_no_provider_health_findings(self):
        providers = [_healthy_provider("local_ollama", "local"), _healthy_provider("claude", "premium")]
        findings = build_diagnostics(
            providers=providers,
            ai_mode="hybrid_recommended",
            require_premium_approval=False,
            routing_outcomes=[],
            recent_failures=[],
        )
        self.assertEqual([f for f in findings if f.category == "provider_health"], [])

    def test_disabled_provider_is_info_severity(self):
        providers = [ProviderHealthInput(provider_key="openai", label="OpenAI", tier="premium", enabled=False, configured=False)]
        findings = build_diagnostics(
            providers=providers, ai_mode="hybrid_recommended", require_premium_approval=False,
            routing_outcomes=[], recent_failures=[],
        )
        health = [f for f in findings if f.category == "provider_health"]
        self.assertEqual(len(health), 1)
        self.assertEqual(health[0].severity, "info")
        self.assertEqual(health[0].provider_key, "openai")
        self.assertIn("disabled", health[0].title)

    def test_enabled_but_unconfigured_provider_is_warning_severity(self):
        providers = [ProviderHealthInput(provider_key="groq", label="Groq", tier="free", enabled=True, configured=False)]
        findings = build_diagnostics(
            providers=providers, ai_mode="hybrid_recommended", require_premium_approval=False,
            routing_outcomes=[], recent_failures=[],
        )
        health = [f for f in findings if f.category == "provider_health"]
        self.assertEqual(len(health), 1)
        self.assertEqual(health[0].severity, "warning")
        self.assertIn("not configured", health[0].title)

    def test_disabled_takes_precedence_over_unconfigured(self):
        # A provider that is BOTH disabled and unconfigured must only ever
        # produce the "disabled" (info) finding, never a second "enabled
        # but not configured" (warning) one for the same provider - the
        # two conditions are mutually exclusive by construction (elif),
        # confirmed explicitly here.
        providers = [ProviderHealthInput(provider_key="openai", label="OpenAI", tier="premium", enabled=False, configured=False)]
        findings = build_diagnostics(
            providers=providers, ai_mode="hybrid_recommended", require_premium_approval=False,
            routing_outcomes=[], recent_failures=[],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "info")


class TestConfigurationFindings(unittest.TestCase):
    def test_local_only_with_no_local_configured_is_error(self):
        providers = [ProviderHealthInput(provider_key="local_ollama", label="Ollama", tier="local", enabled=True, configured=False)]
        findings = build_diagnostics(
            providers=providers, ai_mode="local_only", require_premium_approval=False,
            routing_outcomes=[], recent_failures=[],
        )
        config_findings = [f for f in findings if f.category == "configuration"]
        self.assertEqual(len(config_findings), 1)
        self.assertEqual(config_findings[0].severity, "error")
        self.assertIn("local_only", config_findings[0].title)

    def test_local_only_with_local_configured_has_no_configuration_error(self):
        providers = [_healthy_provider("local_ollama", "local")]
        findings = build_diagnostics(
            providers=providers, ai_mode="local_only", require_premium_approval=False,
            routing_outcomes=[], recent_failures=[],
        )
        self.assertEqual([f for f in findings if f.category == "configuration"], [])

    def test_premium_only_with_no_premium_configured_is_error(self):
        providers = [ProviderHealthInput(provider_key="claude", label="Claude", tier="premium", enabled=True, configured=False)]
        findings = build_diagnostics(
            providers=providers, ai_mode="premium_only", require_premium_approval=False,
            routing_outcomes=[], recent_failures=[],
        )
        config_findings = [f for f in findings if f.category == "configuration"]
        self.assertEqual(len(config_findings), 1)
        self.assertEqual(config_findings[0].severity, "error")
        self.assertIn("premium_only", config_findings[0].title)

    def test_require_approval_with_no_premium_configured_is_warning(self):
        providers = [_healthy_provider("local_ollama", "local")]
        findings = build_diagnostics(
            providers=providers, ai_mode="hybrid_recommended", require_premium_approval=True,
            routing_outcomes=[], recent_failures=[],
        )
        config_findings = [f for f in findings if f.category == "configuration"]
        self.assertEqual(len(config_findings), 1)
        self.assertEqual(config_findings[0].severity, "warning")
        self.assertIn("approval", config_findings[0].title.lower())

    def test_require_approval_with_premium_configured_has_no_finding(self):
        providers = [_healthy_provider("local_ollama", "local"), _healthy_provider("claude", "premium")]
        findings = build_diagnostics(
            providers=providers, ai_mode="hybrid_recommended", require_premium_approval=True,
            routing_outcomes=[], recent_failures=[],
        )
        self.assertEqual([f for f in findings if f.category == "configuration"], [])

    def test_require_approval_under_local_only_is_not_flagged(self):
        # local_only never reaches premium at all - requiring approval is
        # irrelevant in that mode, so this must not ALSO produce the
        # "no premium configured" warning on top of the local_only error.
        providers = [_healthy_provider("local_ollama", "local")]
        findings = build_diagnostics(
            providers=providers, ai_mode="local_only", require_premium_approval=True,
            routing_outcomes=[], recent_failures=[],
        )
        config_findings = [f for f in findings if f.category == "configuration"]
        self.assertEqual(len(config_findings), 0)


class TestRoutingOutcomeFindings(unittest.TestCase):
    def test_success_outcome_produces_no_finding(self):
        findings = build_diagnostics(
            providers=[], ai_mode="hybrid_recommended", require_premium_approval=False,
            routing_outcomes=[RoutingOutcomeInput(capability="research_analysis", feature_label="Prospect Research", outcome="success")],
            recent_failures=[],
        )
        self.assertEqual([f for f in findings if f.category == "routing"], [])

    def test_failed_outcome_is_error(self):
        findings = build_diagnostics(
            providers=[], ai_mode="hybrid_recommended", require_premium_approval=False,
            routing_outcomes=[RoutingOutcomeInput(capability="research_analysis", feature_label="Prospect Research", outcome="failed")],
            recent_failures=[],
        )
        routing = [f for f in findings if f.category == "routing"]
        self.assertEqual(len(routing), 1)
        self.assertEqual(routing[0].severity, "error")
        self.assertEqual(routing[0].capability, "research_analysis")

    def test_waiting_outcome_is_info(self):
        findings = build_diagnostics(
            providers=[], ai_mode="hybrid_recommended", require_premium_approval=True,
            routing_outcomes=[RoutingOutcomeInput(capability="outreach_email_generation", feature_label="Email Drafting", outcome="waiting")],
            recent_failures=[],
        )
        routing = [f for f in findings if f.category == "routing"]
        self.assertEqual(len(routing), 1)
        self.assertEqual(routing[0].severity, "info")


class TestRecentFailureFindings(unittest.TestCase):
    def test_low_count_failure_is_warning(self):
        findings = build_diagnostics(
            providers=[], ai_mode="hybrid_recommended", require_premium_approval=False,
            routing_outcomes=[],
            recent_failures=[FailureSummaryInput(provider_key="groq", label="Groq", error_type="ProviderTimeoutError", count=2)],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "warning")
        self.assertEqual(findings[0].category, "routing")
        self.assertIn("2 times", findings[0].title)

    def test_high_count_failure_escalates_to_error(self):
        findings = build_diagnostics(
            providers=[], ai_mode="hybrid_recommended", require_premium_approval=False,
            routing_outcomes=[],
            recent_failures=[FailureSummaryInput(provider_key="claude", label="Claude", error_type="AuthenticationError", count=5)],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "error")

    def test_singular_count_uses_singular_wording(self):
        findings = build_diagnostics(
            providers=[], ai_mode="hybrid_recommended", require_premium_approval=False,
            routing_outcomes=[],
            recent_failures=[FailureSummaryInput(provider_key="groq", label="Groq", error_type="ProviderTimeoutError", count=1)],
        )
        self.assertIn("1 time ", findings[0].title)
        self.assertNotIn("1 times", findings[0].title)


class TestNoFindings(unittest.TestCase):
    def test_fully_healthy_gateway_produces_zero_findings(self):
        providers = [_healthy_provider("local_ollama", "local"), _healthy_provider("groq", "free"), _healthy_provider("claude", "premium")]
        findings = build_diagnostics(
            providers=providers,
            ai_mode="hybrid_recommended",
            require_premium_approval=True,
            routing_outcomes=[RoutingOutcomeInput(capability="research_analysis", feature_label="Prospect Research", outcome="success")],
            recent_failures=[],
        )
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
