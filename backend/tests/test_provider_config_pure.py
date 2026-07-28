"""
M8.3 (AI Gateway Management & Control, Step 1) - pure tests for
app.ai_gateway.provider_config. Genuinely executable in this project's
authoring sandbox (no pydantic_settings, no sqlalchemy - same disclosed
convention as tests/test_local_model_policy_pure.py):

  - `_encrypt_api_key`/`_decrypt_api_key` are tested for real, via the
    real `cryptography` package (which IS installed in this sandbox,
    unlike sqlalchemy/pydantic_settings) and the module's own
    `settings_obj` DI seam (same convention
    `app.ai_gateway.local_model_policy.resolve_local_model()` already
    established) - no monkeypatching of `app.core.config` needed.
  - `resolve_provider_config()` is tested for its documented "fail OPEN
    to the given fallback values" behavior when the DB layer is
    unavailable - and in THIS sandbox specifically, that isn't a
    simulation: sqlalchemy genuinely isn't importable here, so calling
    this function for real genuinely exercises its own
    `except Exception: return <fallback-only ResolvedProviderConfig>`
    branch, not a mock standing in for it.

NOT covered here (needs Docker/Postgres - belongs in
tests/test_provider_config_e2e.py): `resolve_provider_config()` actually
reading back a saved `AIProviderConfig` row, and `save_provider_config()`'s
audit-trail behavior (one row per changed field set, no row when nothing
changed, never a plaintext api_key in `field_changes`).

Run standalone with:
    python -m unittest tests.test_provider_config_pure
"""
import unittest

from cryptography.fernet import Fernet

from app.ai_gateway.provider_config import (
    ResolvedProviderConfig,
    _decrypt_api_key,
    _encrypt_api_key,
    _get_fernet,
    resolve_provider_config,
)


class _FakeSettings:
    """Minimal stand-in for app.core.config.settings - only the one
    attribute this module actually reads."""

    def __init__(self, CREDENTIAL_ENCRYPTION_KEY=None):
        self.CREDENTIAL_ENCRYPTION_KEY = CREDENTIAL_ENCRYPTION_KEY


class TestResolvedProviderConfig(unittest.TestCase):
    def test_extra_settings_defaults_to_empty_dict_not_shared_mutable(self):
        a = ResolvedProviderConfig(enabled=True, api_key=None, base_url=None, default_model=None)
        b = ResolvedProviderConfig(enabled=True, api_key=None, base_url=None, default_model=None)
        a.extra_settings["x"] = 1
        self.assertEqual(b.extra_settings, {})


class TestGetFernet(unittest.TestCase):
    def test_returns_none_when_key_unset(self):
        self.assertIsNone(_get_fernet(settings_obj=_FakeSettings(CREDENTIAL_ENCRYPTION_KEY=None)))

    def test_returns_none_when_key_invalid(self):
        self.assertIsNone(_get_fernet(settings_obj=_FakeSettings(CREDENTIAL_ENCRYPTION_KEY="not-a-real-fernet-key")))

    def test_returns_fernet_for_a_real_key(self):
        key = Fernet.generate_key().decode()
        fernet = _get_fernet(settings_obj=_FakeSettings(CREDENTIAL_ENCRYPTION_KEY=key))
        self.assertIsInstance(fernet, Fernet)


class TestEncryptDecryptApiKey(unittest.TestCase):
    def setUp(self):
        self.key = Fernet.generate_key().decode()
        self.settings = _FakeSettings(CREDENTIAL_ENCRYPTION_KEY=self.key)

    def test_round_trip(self):
        ciphertext = _encrypt_api_key("sk-real-secret-value", settings_obj=self.settings)
        self.assertIsNotNone(ciphertext)
        self.assertNotIn("sk-real-secret-value", ciphertext)
        self.assertEqual(_decrypt_api_key(ciphertext, settings_obj=self.settings), "sk-real-secret-value")

    def test_encrypt_none_or_empty_returns_none(self):
        self.assertIsNone(_encrypt_api_key(None, settings_obj=self.settings))
        self.assertIsNone(_encrypt_api_key("", settings_obj=self.settings))

    def test_decrypt_none_or_empty_returns_none(self):
        self.assertIsNone(_decrypt_api_key(None, settings_obj=self.settings))
        self.assertIsNone(_decrypt_api_key("", settings_obj=self.settings))

    def test_encrypt_raises_when_key_unset(self):
        with self.assertRaises(ValueError):
            _encrypt_api_key("sk-real-secret-value", settings_obj=_FakeSettings(CREDENTIAL_ENCRYPTION_KEY=None))

    def test_decrypt_returns_none_when_key_unset_never_raises(self):
        ciphertext = _encrypt_api_key("sk-real-secret-value", settings_obj=self.settings)
        self.assertIsNone(_decrypt_api_key(ciphertext, settings_obj=_FakeSettings(CREDENTIAL_ENCRYPTION_KEY=None)))

    def test_decrypt_returns_none_on_wrong_key_never_raises(self):
        ciphertext = _encrypt_api_key("sk-real-secret-value", settings_obj=self.settings)
        wrong_settings = _FakeSettings(CREDENTIAL_ENCRYPTION_KEY=Fernet.generate_key().decode())
        self.assertIsNone(_decrypt_api_key(ciphertext, settings_obj=wrong_settings))

    def test_decrypt_returns_none_on_corrupted_ciphertext_never_raises(self):
        self.assertIsNone(_decrypt_api_key("not-a-real-fernet-token", settings_obj=self.settings))


class TestResolveProviderConfigFailsOpenWithoutDb(unittest.TestCase):
    """This sandbox genuinely has no sqlalchemy installed (confirmed the
    same way every prior milestone's own tests disclose) - calling
    resolve_provider_config() here for real exercises its documented
    "DB layer unavailable -> fail open to fallback values" branch for
    real, not a simulated stand-in for it."""

    def test_falls_back_to_given_values_when_db_layer_unavailable(self):
        config = resolve_provider_config(
            "claude",
            fallback_enabled=True,
            fallback_api_key="fallback-key",
            fallback_base_url="fallback-base-url",
            fallback_default_model="fallback-model",
        )
        self.assertEqual(
            config,
            ResolvedProviderConfig(
                enabled=True,
                api_key="fallback-key",
                base_url="fallback-base-url",
                default_model="fallback-model",
            ),
        )

    def test_falls_back_to_defaults_when_no_fallback_given(self):
        config = resolve_provider_config("claude")
        self.assertTrue(config.enabled)
        self.assertIsNone(config.api_key)
        self.assertIsNone(config.base_url)
        self.assertIsNone(config.default_model)
        self.assertEqual(config.extra_settings, {})


if __name__ == "__main__":
    unittest.main()
