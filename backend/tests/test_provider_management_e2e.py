"""
M8.3 (AI Gateway Management & Control, Step 2 - Provider Management) -
real-DB / real-route coverage. Same conventions as
test_provider_config_e2e.py (Step 1's own e2e file) and
test_discovery_providers_route.py (calls route functions directly rather
than a real HTTP request/FastAPI TestClient - the FastAPI dependency
WIRING itself - `Depends(get_current_active_admin)` actually 403ing an
unauthenticated request - is framework-level and already proven by the
pre-existing POST /auth/register precedent this reuses; what's new and
worth testing here is each route FUNCTION's own logic once a
current_user is already resolved).

Requires a real database connection - not runnable in this authoring
sandbox (no Docker/Postgres access, and pydantic/sqlalchemy aren't even
importable here - see test_provider_config_e2e.py's own disclosure).
Only py_compile-checked in the authoring sandbox; run for real via
verify_m8_3_step2_provider_management.sh, in Docker.

Covers:
  - ui_query.get_provider_config()/list_provider_config_audit() against a
    real DB (the "no row yet -> synthesized default" path, and the
    "row exists -> reflects it, including updated_by_user_email" path).
  - The four new routes in app/api/routes/ai_gateway.py: PUT/GET
    .../config, GET .../config/audit, POST .../test-connection - each
    called as a plain function (not through FastAPI's routing layer),
    passing an already-resolved `current_user`/`db` directly, exactly
    like test_discovery_providers_route.py's own precedent.
  - get_current_active_admin() itself (the actual admin-gate function,
    reused verbatim from the existing POST /auth/register precedent) -
    403s for a non-admin, passes a real admin through unchanged.

Uses two temporary, monkeypatched PROVIDER_CLIENT_REGISTRY entries for
the duration of this module's tests (never a real provider_key) so
`ui_query.get_provider_config()`'s own "provider_key not in registry ->
None" guard, and the routes' own 404 checks, exercise a REAL registry
membership check without ever touching (or risking leftover state in)
one of the six real, shared provider_key rows every other e2e test in
this project may also be reading/writing.

Run standalone with:
    python -m unittest tests.test_provider_management_e2e
"""
import unittest
import uuid

from fastapi import HTTPException

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal

from app.ai_gateway import ui_query
from app.ai_gateway.provider_config import save_provider_config
from app.ai_gateway.providers.base import ConnectionTestResult, ProviderClient
from app.ai_gateway.providers.registry import PROVIDER_CLIENT_REGISTRY
from app.ai_gateway.request import GatewayRequest, GatewayResponse
from app.api.deps import get_current_active_admin
from app.api.routes.ai_gateway import (
    get_provider_config as route_get_provider_config,
    list_provider_config_audit as route_list_provider_config_audit,
    put_provider_config as route_put_provider_config,
    test_provider_connection as route_test_provider_connection,
)
from app.models.ai_provider_config import AIProviderConfig
from app.models.ai_provider_config_audit import AIProviderConfigAudit
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.ai_gateway import ProviderConfigWrite


class _FakeConfigProviderClient(ProviderClient):
    """Registered only for the duration of this module's tests - never a
    real provider_key (see module docstring for why)."""

    key = "test_m8_3_step2_config_provider"

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        raise NotImplementedError

    def is_configured(self) -> bool:
        return True


class _FakeConnectionTestClient(ProviderClient):
    key = "test_m8_3_step2_conn_provider"

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        raise NotImplementedError

    def is_configured(self) -> bool:
        return True

    def test_connection(self) -> ConnectionTestResult:
        # A fixed, deterministic result - proves the route wires
        # provider_cls().test_connection() through end to end without
        # ever making a real network call (same "never call a real SDK
        # in an automated test" discipline test_provider_config_e2e.py's
        # own TestRealProviderClientReflectsOverride class established
        # for is_configured()/default_model, applied here to
        # test_connection() instead).
        return ConnectionTestResult(success=True, message="Connected", latency_ms=42.0, available_models=["fake-model-1"])


class ProviderManagementTestBase(unittest.TestCase):
    CONFIG_PROVIDER_KEY = _FakeConfigProviderClient.key
    CONN_PROVIDER_KEY = _FakeConnectionTestClient.key

    def setUp(self):
        self.db = SessionLocal()
        self.admin = User(email=f"m8-3-step2-admin-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.non_admin = User(email=f"m8-3-step2-user-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.OPERATOR)
        self.db.add(self.admin)
        self.db.add(self.non_admin)
        self.db.commit()

        PROVIDER_CLIENT_REGISTRY[self.CONFIG_PROVIDER_KEY] = _FakeConfigProviderClient
        PROVIDER_CLIENT_REGISTRY[self.CONN_PROVIDER_KEY] = _FakeConnectionTestClient

    def tearDown(self):
        del PROVIDER_CLIENT_REGISTRY[self.CONFIG_PROVIDER_KEY]
        del PROVIDER_CLIENT_REGISTRY[self.CONN_PROVIDER_KEY]

        self.db.query(AIProviderConfigAudit).filter(
            AIProviderConfigAudit.provider_key == self.CONFIG_PROVIDER_KEY
        ).delete(synchronize_session=False)
        self.db.query(AIProviderConfig).filter(AIProviderConfig.provider_key == self.CONFIG_PROVIDER_KEY).delete(
            synchronize_session=False
        )
        self.db.commit()
        self.db.query(User).filter(User.id.in_([self.admin.id, self.non_admin.id])).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()


class TestGetCurrentActiveAdmin(ProviderManagementTestBase):
    def test_admin_passes_through_unchanged(self):
        self.assertIs(get_current_active_admin(current_user=self.admin), self.admin)

    def test_non_admin_raises_403(self):
        with self.assertRaises(HTTPException) as ctx:
            get_current_active_admin(current_user=self.non_admin)
        self.assertEqual(ctx.exception.status_code, 403)


class TestUiQueryGetProviderConfig(ProviderManagementTestBase):
    def test_unregistered_provider_key_returns_none(self):
        self.assertIsNone(ui_query.get_provider_config(self.db, "definitely_not_a_registered_provider"))

    def test_no_saved_row_synthesizes_default(self):
        config = ui_query.get_provider_config(self.db, self.CONFIG_PROVIDER_KEY)
        self.assertIsNotNone(config)
        self.assertEqual(config.provider_key, self.CONFIG_PROVIDER_KEY)
        self.assertTrue(config.enabled)
        self.assertFalse(config.has_api_key)
        self.assertIsNone(config.base_url)
        self.assertIsNone(config.default_model)
        self.assertEqual(config.extra_settings, {})
        self.assertIsNone(config.updated_at)
        self.assertIsNone(config.updated_by_user_email)

    def test_saved_row_is_reflected_including_updater_email(self):
        save_provider_config(
            self.db, self.CONFIG_PROVIDER_KEY, changed_by_user_id=self.admin.id, enabled=False, base_url="https://example.test"
        )
        self.db.commit()

        config = ui_query.get_provider_config(self.db, self.CONFIG_PROVIDER_KEY)
        self.assertFalse(config.enabled)
        self.assertEqual(config.base_url, "https://example.test")
        self.assertEqual(config.updated_by_user_email, self.admin.email)
        self.assertIsNotNone(config.updated_at)


class TestConfigRoutes(ProviderManagementTestBase):
    def test_put_unknown_provider_404(self):
        with self.assertRaises(HTTPException) as ctx:
            route_put_provider_config(
                "definitely_not_a_registered_provider", ProviderConfigWrite(), db=self.db, current_user=self.admin
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_get_unknown_provider_404(self):
        with self.assertRaises(HTTPException) as ctx:
            route_get_provider_config("definitely_not_a_registered_provider", db=self.db, current_user=self.admin)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_put_then_get_round_trip(self):
        result = route_put_provider_config(
            self.CONFIG_PROVIDER_KEY,
            ProviderConfigWrite(enabled=False, base_url="https://example.test", default_model="foo-model"),
            db=self.db,
            current_user=self.admin,
        )
        self.assertFalse(result.enabled)
        self.assertEqual(result.base_url, "https://example.test")
        self.assertEqual(result.default_model, "foo-model")
        self.assertEqual(result.updated_by_user_email, self.admin.email)

        fetched = route_get_provider_config(self.CONFIG_PROVIDER_KEY, db=self.db, current_user=self.admin)
        self.assertEqual(fetched.base_url, "https://example.test")
        self.assertEqual(fetched.default_model, "foo-model")

    def test_audit_route_reflects_two_saves_most_recent_first(self):
        route_put_provider_config(self.CONFIG_PROVIDER_KEY, ProviderConfigWrite(enabled=False), db=self.db, current_user=self.admin)
        route_put_provider_config(self.CONFIG_PROVIDER_KEY, ProviderConfigWrite(enabled=True), db=self.db, current_user=self.admin)

        entries = route_list_provider_config_audit(self.CONFIG_PROVIDER_KEY, limit=50, db=self.db, current_user=self.admin)
        self.assertEqual(len(entries), 2)
        # Most-recent-first: the second save (False -> True) comes back first.
        self.assertEqual(entries[0].field_changes["enabled"], {"old": False, "new": True})
        self.assertEqual(entries[1].field_changes["enabled"], {"old": True, "new": False})
        for entry in entries:
            self.assertEqual(entry.changed_by_user_email, self.admin.email)

    def test_audit_route_unknown_provider_404(self):
        with self.assertRaises(HTTPException) as ctx:
            route_list_provider_config_audit("definitely_not_a_registered_provider", limit=50, db=self.db, current_user=self.admin)
        self.assertEqual(ctx.exception.status_code, 404)


class TestTestConnectionRoute(ProviderManagementTestBase):
    def test_unknown_provider_404(self):
        with self.assertRaises(HTTPException) as ctx:
            route_test_provider_connection("definitely_not_a_registered_provider", current_user=self.non_admin)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_not_admin_gated_any_authenticated_user_can_call_it(self):
        # Deliberately passes a NON-admin user - see the route's own
        # docstring for why this is intentional (never mutates anything,
        # never exposes a credential).
        result = route_test_provider_connection(self.CONN_PROVIDER_KEY, current_user=self.non_admin)
        self.assertTrue(result.success)
        self.assertEqual(result.provider_key, self.CONN_PROVIDER_KEY)
        self.assertEqual(result.latency_ms, 42.0)
        self.assertEqual(result.available_models, ["fake-model-1"])


if __name__ == "__main__":
    unittest.main()
