"""
M8.3 (AI Gateway Management & Control, Step 3 - Model Role Management) -
pure, zero-third-party-dependency tests for
`app.ai_gateway.local_model_policy.resolve_local_model()`'s NEW DB-override
resolution order, added this step. Genuinely executable in this project's
authoring sandbox (no pydantic_settings, no sqlalchemy - same disclosed
convention as `tests/test_local_model_policy_pure.py`) via the function's
own `db_lookup` DI seam - see that function's docstring for why this
exists (identical pattern to `settings_obj`, one level up).

NOT covered here (needs Docker/Postgres - belongs in
tests/test_model_role_management_e2e.py instead): the real
`_resolve_db_model_for_role()` DB round trip, `list_model_roles()`/
`save_model_role()`/`delete_model_role()` (all genuinely query
`app.models.ai_model_role.AIModelRole` via SQLAlchemy), and the new
GET/PUT/DELETE `/ai-gateway/model-roles*` routes.

`tests/test_local_model_policy_pure.py` (unchanged, still passing - see
its own suite in the full regression sweep) already covers every
settings-only branch this module had BEFORE this step; this file adds
ONLY the new DB-layer-related branches Step 3 introduces.
"""
import unittest

from app.ai_gateway.local_model_policy import resolve_local_model


class _FakeSettings:
    """Minimal stand-in for app.core.config.settings - only the
    attributes this module actually reads."""

    def __init__(self, LOCAL_MODEL_DEFAULT_MODEL=None, LOCAL_MODEL_SECONDARY_MODEL=None):
        self.LOCAL_MODEL_DEFAULT_MODEL = LOCAL_MODEL_DEFAULT_MODEL
        self.LOCAL_MODEL_SECONDARY_MODEL = LOCAL_MODEL_SECONDARY_MODEL


def _fake_db_lookup(overrides: dict) -> callable:
    """Builds a `db_lookup` callable backed by a plain dict - the pure
    stand-in for a real `ai_model_roles` table, same "any object/callable
    satisfying the seam's shape" testability convention every other DI
    seam in this codebase already uses. A role name absent from
    `overrides` behaves exactly like "no DB row for this role" (or a
    disabled one) - returns None, same as the real
    `_resolve_db_model_for_role()` would."""
    return lambda role_name: overrides.get(role_name)


class TestResolveLocalModelDbOverride(unittest.TestCase):
    def test_db_override_wins_over_settings_for_the_first_preferred_role(self):
        # "research_analysis" prefers only the "research" role.
        settings_obj = _FakeSettings(LOCAL_MODEL_DEFAULT_MODEL="qwen3:8b")
        db_lookup = _fake_db_lookup({"research": "qwen3:14b-db-override"})
        self.assertEqual(
            resolve_local_model("research_analysis", settings_obj=settings_obj, db_lookup=db_lookup),
            "qwen3:14b-db-override",
        )

    def test_no_db_row_for_the_role_falls_through_to_settings(self):
        settings_obj = _FakeSettings(LOCAL_MODEL_DEFAULT_MODEL="qwen3:8b")
        db_lookup = _fake_db_lookup({})  # nothing saved in the DB layer at all
        self.assertEqual(
            resolve_local_model("research_analysis", settings_obj=settings_obj, db_lookup=db_lookup),
            "qwen3:8b",
        )

    def test_disabled_db_row_behaves_like_absent_and_falls_through(self):
        # _resolve_db_model_for_role()'s real implementation filters
        # enabled=True at the query level, so a disabled row is
        # indistinguishable from "no row" to this function - the fake
        # models that by simply not including the role's key.
        settings_obj = _FakeSettings(LOCAL_MODEL_DEFAULT_MODEL="qwen3:8b")
        db_lookup = _fake_db_lookup({"research": None})
        self.assertEqual(
            resolve_local_model("research_analysis", settings_obj=settings_obj, db_lookup=db_lookup),
            "qwen3:8b",
        )

    def test_db_override_on_a_later_role_in_the_preference_list_is_still_found(self):
        # "outreach_email_generation" prefers ["writing", "research"] -
        # no DB row and no settings value for "writing", but a DB
        # override IS set for "research" (the second-preferred role).
        settings_obj = _FakeSettings(LOCAL_MODEL_DEFAULT_MODEL=None, LOCAL_MODEL_SECONDARY_MODEL=None)
        db_lookup = _fake_db_lookup({"research": "qwen3:14b-db-override"})
        self.assertEqual(
            resolve_local_model("outreach_email_generation", settings_obj=settings_obj, db_lookup=db_lookup),
            "qwen3:14b-db-override",
        )

    def test_writing_role_db_override_beats_research_role_settings_fallback(self):
        # The full precedence chain in one assertion: "writing" has a DB
        # override, "research" only has a settings value - "writing"
        # (first-preferred) must win, via the DB layer, without ever
        # looking at "research" at all.
        settings_obj = _FakeSettings(LOCAL_MODEL_DEFAULT_MODEL="qwen3:8b")
        db_lookup = _fake_db_lookup({"writing": "llama3.1:8b-db-override"})
        self.assertEqual(
            resolve_local_model("outreach_email_generation", settings_obj=settings_obj, db_lookup=db_lookup),
            "llama3.1:8b-db-override",
        )

    def test_empty_string_from_db_lookup_treated_as_unconfigured(self):
        # Same "" is falsy convention as the settings layer - defensive,
        # since the real _resolve_db_model_for_role() itself already
        # guards against returning an empty `model` (see its own
        # docstring), but this function must not assume that.
        settings_obj = _FakeSettings(LOCAL_MODEL_DEFAULT_MODEL="qwen3:8b")
        db_lookup = _fake_db_lookup({"research": ""})
        self.assertEqual(
            resolve_local_model("research_analysis", settings_obj=settings_obj, db_lookup=db_lookup),
            "qwen3:8b",
        )

    def test_nothing_configured_in_either_layer_returns_none(self):
        settings_obj = _FakeSettings()
        db_lookup = _fake_db_lookup({})
        self.assertIsNone(resolve_local_model("research_analysis", settings_obj=settings_obj, db_lookup=db_lookup))

    def test_default_db_lookup_is_the_real_function_and_fails_open_when_sqlalchemy_absent(self):
        # No db_lookup passed at all - exercises the REAL
        # _resolve_db_model_for_role() genuinely, in this sandbox, which
        # genuinely has no sqlalchemy installed - so this really does
        # take the documented "DB layer unavailable -> fail open" branch,
        # not a simulated stand-in for it (identical disclosure to
        # tests/test_provider_config_pure.py's own resolve_provider_config()
        # coverage). Confirms passing no db_lookup at all still resolves
        # correctly via the settings-only path, unchanged from pre-Step-3
        # behavior.
        settings_obj = _FakeSettings(LOCAL_MODEL_DEFAULT_MODEL="qwen3:8b")
        self.assertEqual(resolve_local_model("research_analysis", settings_obj=settings_obj), "qwen3:8b")


if __name__ == "__main__":
    unittest.main()
