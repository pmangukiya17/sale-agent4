"""
M8.2 addendum (approved 2026-07-28) - pure, zero-third-party-dependency
tests for app.ai_gateway.local_model_policy. Genuinely executable in this
project's authoring sandbox (no pydantic_settings, no sqlalchemy - same
disclosed convention as tests/test_ai_provider_hierarchy_pure.py) via
resolve_local_model()'s own `settings_obj` DI seam - see that function's
docstring for why this exists.

NOT covered here (needs Docker/openai SDK - would belong in an e2e test):
LocalOllamaProviderClient._resolve_model()'s real end-to-end wiring
through OpenAICompatibleProviderClient.complete(), since that subclasses
ProviderClient and imports `openai` at module level.
"""
import unittest

from app.ai_gateway.local_model_policy import (
    CAPABILITY_LOCAL_MODEL_ROLE,
    LOCAL_MODEL_ROLES,
    resolve_local_model,
)


class _FakeSettings:
    """Minimal stand-in for app.core.config.settings - only the
    attributes this module actually reads."""

    def __init__(self, LOCAL_MODEL_DEFAULT_MODEL=None, LOCAL_MODEL_SECONDARY_MODEL=None):
        self.LOCAL_MODEL_DEFAULT_MODEL = LOCAL_MODEL_DEFAULT_MODEL
        self.LOCAL_MODEL_SECONDARY_MODEL = LOCAL_MODEL_SECONDARY_MODEL


class TestLocalModelRoles(unittest.TestCase):
    def test_research_and_writing_roles_registered(self):
        self.assertEqual(LOCAL_MODEL_ROLES["research"], "LOCAL_MODEL_DEFAULT_MODEL")
        self.assertEqual(LOCAL_MODEL_ROLES["writing"], "LOCAL_MODEL_SECONDARY_MODEL")

    def test_no_positional_role_names_leaked_in(self):
        # The whole point of the CEO's requested refinement - "default"/
        # "secondary" must never appear as ROLE names (only as the
        # settings attribute names the roles point AT).
        self.assertNotIn("default", LOCAL_MODEL_ROLES)
        self.assertNotIn("secondary", LOCAL_MODEL_ROLES)


class TestCapabilityLocalModelRole(unittest.TestCase):
    def test_research_analysis_prefers_research_role_only(self):
        self.assertEqual(CAPABILITY_LOCAL_MODEL_ROLE["research_analysis"], ["research"])

    def test_outreach_email_generation_prefers_writing_then_research(self):
        self.assertEqual(CAPABILITY_LOCAL_MODEL_ROLE["outreach_email_generation"], ["writing", "research"])

    def test_forward_looking_placeholders_present_and_inert(self):
        # Disclosed in the module's own docstring - neither capability has
        # live Gateway traffic yet, but both should already resolve
        # sanely once they do.
        self.assertIn("buyer_discovery", CAPABILITY_LOCAL_MODEL_ROLE)
        self.assertIn("crm_data_extraction", CAPABILITY_LOCAL_MODEL_ROLE)


class TestResolveLocalModel(unittest.TestCase):
    def test_research_analysis_resolves_default_model(self):
        settings_obj = _FakeSettings(LOCAL_MODEL_DEFAULT_MODEL="qwen3:8b", LOCAL_MODEL_SECONDARY_MODEL="llama3.1:8b")
        self.assertEqual(resolve_local_model("research_analysis", settings_obj=settings_obj), "qwen3:8b")

    def test_outreach_email_generation_prefers_secondary_model(self):
        settings_obj = _FakeSettings(LOCAL_MODEL_DEFAULT_MODEL="qwen3:8b", LOCAL_MODEL_SECONDARY_MODEL="llama3.1:8b")
        self.assertEqual(resolve_local_model("outreach_email_generation", settings_obj=settings_obj), "llama3.1:8b")

    def test_outreach_email_generation_falls_back_when_secondary_unconfigured(self):
        # The exact "prefer llama3.1:8b, fall back to qwen3:8b if
        # unavailable" requirement - LOCAL_MODEL_SECONDARY_MODEL unset.
        settings_obj = _FakeSettings(LOCAL_MODEL_DEFAULT_MODEL="qwen3:8b", LOCAL_MODEL_SECONDARY_MODEL=None)
        self.assertEqual(resolve_local_model("outreach_email_generation", settings_obj=settings_obj), "qwen3:8b")

    def test_unknown_capability_falls_back_to_research_role(self):
        settings_obj = _FakeSettings(LOCAL_MODEL_DEFAULT_MODEL="qwen3:8b")
        self.assertEqual(resolve_local_model("some_future_capability_nobody_mapped", settings_obj=settings_obj), "qwen3:8b")

    def test_nothing_configured_returns_none(self):
        settings_obj = _FakeSettings()
        self.assertIsNone(resolve_local_model("research_analysis", settings_obj=settings_obj))

    def test_empty_string_treated_as_unconfigured(self):
        # "" is falsy - same "unconfigured is normal" convention as every
        # other optional setting in this codebase; must not be returned
        # as if it were a real model id.
        settings_obj = _FakeSettings(LOCAL_MODEL_DEFAULT_MODEL="qwen3:8b", LOCAL_MODEL_SECONDARY_MODEL="")
        self.assertEqual(resolve_local_model("outreach_email_generation", settings_obj=settings_obj), "qwen3:8b")


if __name__ == "__main__":
    unittest.main()
