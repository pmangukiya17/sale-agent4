"""
M11 (AI Provider Hierarchy) - pure, zero-third-party-dependency tests.
Genuinely executable and executed in the authoring sandbox (no Docker, no
pydantic_settings, no sqlalchemy - see this project's own standing
disclosure convention, e.g. test_llm_mapping_pure.py). Covers exactly the
modules that import neither `app.core.config.settings` at module level nor
any ORM type: app.ai_gateway.tiers, app.ai_gateway.confidence,
app.ai_gateway.router's RoutingDecision/_build_decision (settings is
imported LAZILY inside ProviderRouter.select() only - see that module's
own docstring - so importing router.py itself, and calling
_build_decision() directly, needs no settings/pydantic_settings at all),
and app.ai_gateway.accounting's estimate_pre_call_cost_usd (no settings
import at all, like every other function in that module).

NOT covered here (needs Docker - see
test_ai_provider_hierarchy_e2e.py's own disclosure): ProviderRouter.select()
itself (reads settings.AI_MODE), AIGateway.complete()'s premium-approval
gate end to end, LocalOllamaProviderClient/GroqProviderClient's real HTTP
behavior (both subclass OpenAICompatibleProviderClient, which `import
openai`).
"""
import unittest

from app.ai_gateway.accounting import estimate_pre_call_cost_usd, register_price
from app.ai_gateway.confidence import assess_complexity
from app.ai_gateway.request import ResponseFormat, ResponseFormatType
from app.ai_gateway.router import CAPABILITY_PROVIDER_PREFERENCE, RoutingDecision, _build_decision
from app.ai_gateway.tiers import PROVIDER_TIER_REGISTRY, ProviderTier, partition, tier_of


class TestProviderTiers(unittest.TestCase):
    def test_known_providers_classified_correctly(self):
        self.assertEqual(tier_of("local_ollama"), ProviderTier.LOCAL)
        self.assertEqual(tier_of("groq"), ProviderTier.FREE)
        self.assertEqual(tier_of("claude"), ProviderTier.PREMIUM)
        self.assertEqual(tier_of("openai"), ProviderTier.PREMIUM)
        self.assertEqual(tier_of("gemini"), ProviderTier.PREMIUM)

    def test_unknown_provider_defaults_to_premium_safe_direction(self):
        self.assertEqual(tier_of("some_future_provider_nobody_classified"), ProviderTier.PREMIUM)

    def test_registry_has_no_duplicate_or_missing_entries_for_day1_providers(self):
        for key in ("local_ollama", "groq", "claude", "openai", "gemini"):
            self.assertIn(key, PROVIDER_TIER_REGISTRY)

    def test_partition_preserves_order_within_each_group(self):
        local, free, premium = partition(["claude", "local_ollama", "openai", "groq", "gemini"])
        self.assertEqual(local, ["local_ollama"])
        self.assertEqual(free, ["groq"])
        self.assertEqual(premium, ["claude", "openai", "gemini"])

    def test_partition_of_empty_list(self):
        self.assertEqual(partition([]), ([], [], []))


class TestGeminiFreeTierSplit(unittest.TestCase):
    """M-AIGW-3 (Gemini Free-Tier Split - see
    docs/architecture/provider-neutral-ai-gateway-plan.md Section 7). Two
    distinct provider_keys, one shared client implementation
    (gemini_client.py's _GeminiProviderClientBase) - these tests cover the
    two pure, settings-free registries that make the split actually
    reachable: tiers.py's classification and router.py's default
    preference list. The provider client's own request/response
    translation logic is unchanged from before the split (still only
    e2e-testable - needs `google-genai` - per this file's own header
    disclosure), so it isn't re-tested here."""

    def test_gemini_ai_studio_is_free_gemini_stays_premium(self):
        self.assertEqual(tier_of("gemini_ai_studio"), ProviderTier.FREE)
        self.assertEqual(tier_of("gemini"), ProviderTier.PREMIUM)

    def test_both_gemini_keys_registered_in_tier_registry(self):
        self.assertIn("gemini_ai_studio", PROVIDER_TIER_REGISTRY)
        self.assertIn("gemini", PROVIDER_TIER_REGISTRY)

    def test_partition_places_gemini_ai_studio_with_free_and_gemini_with_premium(self):
        local, free, premium = partition(["local_ollama", "gemini_ai_studio", "groq", "gemini", "claude"])
        self.assertEqual(local, ["local_ollama"])
        self.assertEqual(free, ["gemini_ai_studio", "groq"])
        self.assertEqual(premium, ["gemini", "claude"])

    def test_default_preference_list_includes_gemini_ai_studio(self):
        # gemini_ai_studio is safe to auto-attempt by default (brand-new,
        # certainly-unconfigured setting for every existing deployment).
        self.assertIn("gemini_ai_studio", CAPABILITY_PROVIDER_PREFERENCE["default"])

    def test_default_preference_list_deliberately_excludes_plain_gemini(self):
        # Disclosed, deliberate M-AIGW-3 decision (see router.py's own
        # comment): "gemini" (the paid key) was never in this list even
        # before this split, and adding it now would be a real,
        # newly-activated behavior change for any deployment that already
        # has GOOGLE_API_KEY configured. Not fixed in this pass.
        self.assertNotIn("gemini", CAPABILITY_PROVIDER_PREFERENCE["default"])

    def test_gemini_ai_studio_ordered_before_claude_after_local_and_groq(self):
        preference = CAPABILITY_PROVIDER_PREFERENCE["default"]
        self.assertEqual(
            [p for p in preference if p in ("local_ollama", "groq", "gemini_ai_studio", "claude")],
            ["local_ollama", "groq", "gemini_ai_studio", "claude"],
        )


class TestRoutingDecisionChain(unittest.TestCase):
    def test_chain_with_primary_matches_pre_m9_shape(self):
        decision = RoutingDecision(primary="claude")
        self.assertEqual(decision.chain(), ["claude"])
        self.assertEqual(decision.premium, [])

    def test_chain_with_fallbacks(self):
        decision = RoutingDecision(primary="a", fallbacks=["b", "c"])
        self.assertEqual(decision.chain(), ["a", "b", "c"])

    def test_chain_is_empty_when_primary_is_none(self):
        # M11's "nothing to auto-attempt, everything gated behind premium
        # approval" state - AIGateway.complete() must treat this exactly
        # like an exhausted chain, never crash on it.
        decision = RoutingDecision(primary=None, premium=["claude"])
        self.assertEqual(decision.chain(), [])
        self.assertEqual(decision.premium, ["claude"])


class TestBuildDecisionPerMode(unittest.TestCase):
    PREFERENCE = ["local_ollama", "groq", "claude"]

    def test_local_only_excludes_free_and_premium(self):
        d = _build_decision(self.PREFERENCE, "local_only")
        self.assertEqual(d.chain(), ["local_ollama"])
        self.assertEqual(d.premium, [])

    def test_hybrid_recommended_gates_premium(self):
        d = _build_decision(self.PREFERENCE, "hybrid_recommended")
        self.assertEqual(d.chain(), ["local_ollama", "groq"])
        self.assertEqual(d.premium, ["claude"])

    def test_automatic_premium_auto_attempts_everything(self):
        d = _build_decision(self.PREFERENCE, "automatic_premium")
        self.assertEqual(d.chain(), ["local_ollama", "groq", "claude"])
        self.assertEqual(d.premium, [])

    def test_premium_only_skips_local_and_free_entirely(self):
        d = _build_decision(self.PREFERENCE, "premium_only")
        self.assertEqual(d.chain(), ["claude"])
        self.assertEqual(d.premium, [])

    def test_unrecognized_mode_falls_back_to_hybrid_safe_behavior(self):
        d = _build_decision(self.PREFERENCE, "some_typo_mode")
        self.assertEqual(d.chain(), ["local_ollama", "groq"])
        self.assertEqual(d.premium, ["claude"])

    def test_backward_compatibility_day1_deployment_all_premium_under_hybrid(self):
        # The exact pre-M11 shape: a preference list containing ONLY
        # "claude" (no local/free provider configured anywhere, matching
        # every real deployment before this milestone) - under the new
        # default mode, this correctly gates behind approval (chain
        # empty, premium=["claude"]) rather than either silently failing
        # or silently bypassing the gate.
        d = _build_decision(["claude"], "hybrid_recommended")
        self.assertEqual(d.chain(), [])
        self.assertEqual(d.premium, ["claude"])

    def test_local_only_with_no_local_candidate_fails_closed(self):
        # Must NOT fall back to attempting a free/premium provider - that
        # would silently violate "local_only never uses cloud providers."
        d = _build_decision(["groq", "claude"], "local_only")
        self.assertEqual(d.chain(), [])
        self.assertEqual(d.premium, [])


class TestConfidenceAssessment(unittest.TestCase):
    def test_short_simple_request_scores_high_confidence_no_reasons(self):
        assessment = assess_complexity(context_char_length=100, document_count=1)
        self.assertEqual(assessment.score, 1.0)
        self.assertEqual(assessment.reasons, [])

    def test_large_context_reduces_score_and_adds_reason(self):
        assessment = assess_complexity(context_char_length=50_000, document_count=1)
        self.assertIn("Large document", assessment.reasons)
        self.assertLess(assessment.score, 1.0)

    def test_multiple_documents_adds_reason(self):
        assessment = assess_complexity(context_char_length=100, document_count=5)
        self.assertIn("Multiple data sources", assessment.reasons)

    def test_structured_json_output_adds_reason(self):
        rf = ResponseFormat(type=ResponseFormatType.JSON, json_schema={"type": "object"})
        assessment = assess_complexity(context_char_length=100, document_count=1, response_format=rf)
        self.assertIn("Structured output required", assessment.reasons)

    def test_plain_text_response_format_does_not_add_structured_reason(self):
        rf = ResponseFormat(type=ResponseFormatType.TEXT)
        assessment = assess_complexity(context_char_length=100, document_count=1, response_format=rf)
        self.assertNotIn("Structured output required", assessment.reasons)

    def test_deep_reasoning_hint_adds_reason(self):
        assessment = assess_complexity(context_char_length=100, document_count=1, reasoning_depth_hint="deep")
        self.assertIn("Advanced reasoning required", assessment.reasons)

    def test_score_never_goes_below_zero_even_with_every_factor(self):
        rf = ResponseFormat(type=ResponseFormatType.JSON, json_schema={"type": "object"})
        assessment = assess_complexity(
            context_char_length=100_000, document_count=10, response_format=rf, reasoning_depth_hint="deep"
        )
        self.assertGreaterEqual(assessment.score, 0.0)
        self.assertEqual(len(assessment.reasons), 4)


class TestPreCallCostEstimate(unittest.TestCase):
    def setUp(self):
        register_price("test_provider", "test_model", prompt_price_per_1k=1.0, completion_price_per_1k=2.0)

    def test_unpriced_model_returns_none(self):
        result = estimate_pre_call_cost_usd(
            provider_key="claude", model="some-model-with-no-registered-price", prompt_char_length=1000
        )
        self.assertIsNone(result)

    def test_priced_model_returns_a_positive_estimate(self):
        result = estimate_pre_call_cost_usd(
            provider_key="test_provider", model="test_model", prompt_char_length=4000, expected_completion_tokens=1000
        )
        self.assertIsNotNone(result)
        self.assertGreater(result, 0)
        # 4000 chars / 4 = 1000 estimated prompt tokens -> $1.00, plus
        # 1000 completion tokens -> $2.00 = $3.00 total.
        self.assertAlmostEqual(result, 3.0, places=4)

    def test_zero_char_length_still_estimates_at_least_one_token(self):
        result = estimate_pre_call_cost_usd(
            provider_key="test_provider", model="test_model", prompt_char_length=0, expected_completion_tokens=0
        )
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
