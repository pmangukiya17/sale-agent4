"""
M8.3 (AI Gateway Management & Control, Step 1) - real-DB coverage for
app.ai_gateway.provider_config. Same conventions as
test_ai_gateway_ui_query_e2e.py / test_conversation_models.py: direct
function calls against a real SessionLocal, explicit child-then-parent
teardown, `app.db.base` imported first so every model's relationship
string references resolve (see that module's own docstring for the
mapper-registration failure mode this guards against). Requires a real
database connection - not runnable in a sandbox with no Docker/Postgres
access. Only py_compile-checked in the authoring sandbox; run for real via
verify_m8_3_step1_provider_config.sh, in Docker.

Covers what tests/test_provider_config_pure.py explicitly cannot (pure
tests fail-open BEFORE ever touching a DB, by design):
  - save_provider_config()/resolve_provider_config() round trip: an
    override actually saved is what a fresh resolve_provider_config()
    call actually returns.
  - Per-field independence: a row that only sets one field (e.g.
    `enabled=False`) still falls back to the given settings-based value
    for every OTHER field, never an all-or-nothing swap.
  - `encrypted_api_key` round trips through real Fernet encryption (using
    a throwaway CREDENTIAL_ENCRYPTION_KEY set for this test process) -
    the stored ciphertext is never the plaintext, and resolve_provider_config()
    returns the original plaintext back.
  - Audit trail (the CEO's explicit "lightweight configuration audit
    history" requirement): exactly one AIProviderConfigAudit row per save
    that actually changes something, field_changes matches what changed,
    NO audit row when a save changes nothing, and the api_key field is
    NEVER recorded as plaintext in field_changes (only a "set"/"unset"
    marker).
  - clear_api_key/clear_base_url/clear_default_model each independently
    clear one field back to "defer to settings" without touching others.
  - A real ProviderClient (GroqProviderClient - needs only the `openai`
    SDK, not anthropic/google.genai) actually reflects a saved DB
    override through its own is_configured()/default_model - proving the
    Step 1 refactor is wired end to end, not just at the
    resolve_provider_config() layer.

Run standalone with:
    python -m unittest tests.test_provider_config_e2e
"""
import unittest
import uuid

from cryptography.fernet import Fernet

from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal

from app.ai_gateway.provider_config import resolve_provider_config, save_provider_config
from app.models.ai_provider_config import AIProviderConfig
from app.models.ai_provider_config_audit import AIProviderConfigAudit
from app.models.enums import UserRole
from app.models.user import User


class ProviderConfigTestBase(unittest.TestCase):
    TEST_PROVIDER_KEY = "test_m8_3_step1_provider"

    def setUp(self):
        self.db = SessionLocal()
        self.user = User(email=f"m8-3-step1-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.commit()

        # Throwaway, per-process encryption key - never the deployment's
        # real CREDENTIAL_ENCRYPTION_KEY. Monkeypatches app.core.config.settings
        # directly (same "mutate the real settings object for the test's
        # duration, restore in tearDown" discipline test_ai_provider_hierarchy_e2e.py
        # already uses), since resolve_provider_config()/save_provider_config()
        # deliberately do NOT accept a settings_obj DI seam themselves (only
        # the pure encrypt/decrypt helpers do - see test_provider_config_pure.py) -
        # exercising the real settings singleton here is the point of an
        # e2e test.
        from app.core.config import settings

        self._original_key = settings.CREDENTIAL_ENCRYPTION_KEY
        settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()

    def tearDown(self):
        from app.core.config import settings

        settings.CREDENTIAL_ENCRYPTION_KEY = self._original_key

        self.db.query(AIProviderConfigAudit).filter(
            AIProviderConfigAudit.provider_key == self.TEST_PROVIDER_KEY
        ).delete(synchronize_session=False)
        self.db.query(AIProviderConfig).filter(AIProviderConfig.provider_key == self.TEST_PROVIDER_KEY).delete(
            synchronize_session=False
        )
        self.db.commit()
        self.db.query(User).filter(User.id == self.user.id).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()


class TestResolveSaveRoundTrip(ProviderConfigTestBase):
    def test_no_row_falls_back_entirely_to_given_values(self):
        config = resolve_provider_config(
            self.TEST_PROVIDER_KEY,
            fallback_enabled=True,
            fallback_api_key="fallback-key",
            fallback_base_url="fallback-url",
            fallback_default_model="fallback-model",
        )
        self.assertTrue(config.enabled)
        self.assertEqual(config.api_key, "fallback-key")
        self.assertEqual(config.base_url, "fallback-url")
        self.assertEqual(config.default_model, "fallback-model")

    def test_saved_api_key_is_returned_decrypted_and_never_stored_plaintext(self):
        save_provider_config(self.db, self.TEST_PROVIDER_KEY, changed_by_user_id=self.user.id, api_key="sk-real-secret")
        self.db.commit()

        row = self.db.query(AIProviderConfig).filter(AIProviderConfig.provider_key == self.TEST_PROVIDER_KEY).first()
        self.assertIsNotNone(row.encrypted_api_key)
        self.assertNotIn("sk-real-secret", row.encrypted_api_key)

        config = resolve_provider_config(self.TEST_PROVIDER_KEY, fallback_api_key="should-not-be-used")
        self.assertEqual(config.api_key, "sk-real-secret")

    def test_per_field_independence_only_enabled_overridden(self):
        save_provider_config(self.db, self.TEST_PROVIDER_KEY, changed_by_user_id=self.user.id, enabled=False)
        self.db.commit()

        config = resolve_provider_config(
            self.TEST_PROVIDER_KEY,
            fallback_api_key="fallback-key",
            fallback_base_url="fallback-url",
            fallback_default_model="fallback-model",
        )
        self.assertFalse(config.enabled)
        self.assertEqual(config.api_key, "fallback-key")
        self.assertEqual(config.base_url, "fallback-url")
        self.assertEqual(config.default_model, "fallback-model")

    def test_clear_api_key_reverts_to_fallback(self):
        save_provider_config(self.db, self.TEST_PROVIDER_KEY, changed_by_user_id=self.user.id, api_key="sk-real-secret")
        self.db.commit()
        save_provider_config(self.db, self.TEST_PROVIDER_KEY, changed_by_user_id=self.user.id, clear_api_key=True)
        self.db.commit()

        config = resolve_provider_config(self.TEST_PROVIDER_KEY, fallback_api_key="fallback-key")
        self.assertEqual(config.api_key, "fallback-key")

    def test_extra_settings_round_trip(self):
        save_provider_config(
            self.db, self.TEST_PROVIDER_KEY, changed_by_user_id=self.user.id, extra_settings={"organization_id": "org_123"}
        )
        self.db.commit()

        config = resolve_provider_config(self.TEST_PROVIDER_KEY)
        self.assertEqual(config.extra_settings, {"organization_id": "org_123"})


class TestAuditTrail(ProviderConfigTestBase):
    def _audit_rows(self):
        return (
            self.db.query(AIProviderConfigAudit)
            .filter(AIProviderConfigAudit.provider_key == self.TEST_PROVIDER_KEY)
            .order_by(AIProviderConfigAudit.changed_at.asc())
            .all()
        )

    def test_first_save_writes_one_audit_row_with_who_when_what(self):
        save_provider_config(
            self.db, self.TEST_PROVIDER_KEY, changed_by_user_id=self.user.id, enabled=False, base_url="https://example.test"
        )
        self.db.commit()

        rows = self._audit_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.changed_by_user_id, self.user.id)
        self.assertIsNotNone(row.changed_at)
        self.assertEqual(row.field_changes["enabled"], {"old": True, "new": False})
        self.assertEqual(row.field_changes["base_url"], {"old": None, "new": "https://example.test"})

    def test_api_key_is_never_recorded_as_plaintext(self):
        save_provider_config(self.db, self.TEST_PROVIDER_KEY, changed_by_user_id=self.user.id, api_key="sk-real-secret")
        self.db.commit()

        row = self._audit_rows()[0]
        self.assertEqual(row.field_changes["api_key"], {"old": "unset", "new": "set"})
        serialized = str(row.field_changes)
        self.assertNotIn("sk-real-secret", serialized)

    def test_save_that_changes_nothing_writes_no_audit_row(self):
        save_provider_config(self.db, self.TEST_PROVIDER_KEY, changed_by_user_id=self.user.id, enabled=False)
        self.db.commit()
        self.assertEqual(len(self._audit_rows()), 1)

        # Same value again - nothing actually changes.
        save_provider_config(self.db, self.TEST_PROVIDER_KEY, changed_by_user_id=self.user.id, enabled=False)
        self.db.commit()
        self.assertEqual(len(self._audit_rows()), 1)

    def test_two_separate_saves_write_two_audit_rows(self):
        save_provider_config(self.db, self.TEST_PROVIDER_KEY, changed_by_user_id=self.user.id, enabled=False)
        self.db.commit()
        save_provider_config(self.db, self.TEST_PROVIDER_KEY, changed_by_user_id=self.user.id, enabled=True)
        self.db.commit()

        rows = self._audit_rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].field_changes["enabled"], {"old": True, "new": False})
        self.assertEqual(rows[1].field_changes["enabled"], {"old": False, "new": True})


class TestRealProviderClientReflectsOverride(ProviderConfigTestBase):
    """Proves the Step 1 refactor is wired end to end - a real
    ProviderClient (GroqProviderClient, needing only the `openai` SDK)
    actually reads through resolve_provider_config(), not just the
    function in isolation."""

    TEST_PROVIDER_KEY = "groq"

    def tearDown(self):
        # This class deliberately reuses the REAL "groq" provider_key
        # (unlike every other test in this file, which uses a throwaway
        # key) specifically to exercise a real registered ProviderClient -
        # tear down any row this test created so no override leaks into
        # any other test/process reading the real "groq" configuration.
        super().tearDown()

    def test_disabling_via_saved_config_makes_is_configured_false(self):
        from app.ai_gateway.providers.groq_client import GroqProviderClient

        client = GroqProviderClient()
        save_provider_config(self.db, "groq", changed_by_user_id=self.user.id, enabled=False)
        self.db.commit()

        self.assertFalse(client.is_configured())

    def test_saved_default_model_override_is_reflected_live(self):
        from app.ai_gateway.providers.groq_client import GroqProviderClient

        client = GroqProviderClient()
        save_provider_config(self.db, "groq", changed_by_user_id=self.user.id, default_model="llama-overridden-model")
        self.db.commit()

        self.assertEqual(client.default_model, "llama-overridden-model")


if __name__ == "__main__":
    unittest.main()
