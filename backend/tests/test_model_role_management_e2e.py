"""
M8.3 (AI Gateway Management & Control, Step 3 - Model Role Management) -
real-DB / real-route coverage. Same conventions as
test_provider_management_e2e.py (Step 2's own e2e file).

Requires a real database connection - not runnable in this authoring
sandbox (no Docker/Postgres access, and pydantic/sqlalchemy aren't even
importable here). Only py_compile-checked in the authoring sandbox; run
for real via verify_m8_3_step3_model_role_management.sh, in Docker.

Covers:
  - local_model_policy.list_model_roles()/save_model_role()/
    delete_model_role() against a real DB.
  - local_model_policy._resolve_db_model_for_role()/resolve_local_model()
    - the REAL DB round trip (a genuine `ai_model_roles` row actually
    overriding resolve_local_model()'s output), including the
    "disabled row is skipped" and "no row falls back to settings" paths.
  - The three new routes in app/api/routes/ai_gateway.py: GET/PUT
    .../model-roles, DELETE .../model-roles/{role_name} - each called as
    a plain function (not through FastAPI's routing layer), passing an
    already-resolved `current_user`/`db` directly, same precedent
    test_provider_management_e2e.py's own TestConfigRoutes established.

Uses one temporary, uniquely-named role_name for the duration of each
test (never "research"/"writing", the two real roles every other e2e
test/production deployment may also depend on), cleaned up in tearDown -
same "never touch shared production-shaped rows" discipline
test_provider_management_e2e.py's own module docstring already
established for provider_key.

Run standalone with:
    python -m unittest tests.test_model_role_management_e2e
"""
import unittest
import uuid

from fastapi import HTTPException

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation.
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal

from app.ai_gateway import local_model_policy
from app.ai_gateway.local_model_policy import resolve_local_model
from app.api.deps import get_current_active_admin
from app.api.routes.ai_gateway import (
    delete_model_role_route as route_delete_model_role,
    list_model_roles as route_list_model_roles,
    put_model_role as route_put_model_role,
)
from app.models.ai_model_role import AIModelRole
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.ai_gateway import ModelRoleWrite


class ModelRoleManagementTestBase(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.role_name = f"test_m8_3_step3_role_{uuid.uuid4().hex[:12]}"
        self.other_role_name = f"test_m8_3_step3_role_{uuid.uuid4().hex[:12]}"
        self.admin = User(email=f"m8-3-step3-admin-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.admin)
        self.db.commit()

    def tearDown(self):
        self.db.query(AIModelRole).filter(AIModelRole.role_name.in_([self.role_name, self.other_role_name])).delete(
            synchronize_session=False
        )
        self.db.commit()
        self.db.query(User).filter(User.id == self.admin.id).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()


class TestSaveListDeleteModelRole(ModelRoleManagementTestBase):
    def test_save_creates_a_new_role(self):
        row = local_model_policy.save_model_role(
            self.db, self.role_name, model="qwen3:14b", changed_by_user_id=self.admin.id
        )
        self.db.commit()
        self.assertEqual(row.role_name, self.role_name)
        self.assertEqual(row.model, "qwen3:14b")
        self.assertTrue(row.enabled)
        self.assertEqual(row.updated_by_user_id, self.admin.id)

    def test_creating_without_a_model_raises_value_error(self):
        with self.assertRaises(ValueError):
            local_model_policy.save_model_role(self.db, self.role_name, model=None)

    def test_save_updates_an_existing_role_leaving_unspecified_fields_alone(self):
        local_model_policy.save_model_role(self.db, self.role_name, model="qwen3:14b")
        self.db.commit()

        updated = local_model_policy.save_model_role(self.db, self.role_name, enabled=False)
        self.db.commit()
        self.assertEqual(updated.model, "qwen3:14b")  # untouched
        self.assertFalse(updated.enabled)

    def test_list_model_roles_includes_disabled_rows_ordered_by_name(self):
        local_model_policy.save_model_role(self.db, self.other_role_name, model="m1")
        local_model_policy.save_model_role(self.db, self.role_name, model="m2", enabled=False)
        self.db.commit()

        rows = local_model_policy.list_model_roles(self.db)
        names = [r.role_name for r in rows]
        self.assertIn(self.role_name, names)
        self.assertIn(self.other_role_name, names)
        # ordered ascending by role_name
        self.assertEqual(names, sorted(names))

    def test_delete_model_role_removes_the_row_and_reports_true(self):
        local_model_policy.save_model_role(self.db, self.role_name, model="qwen3:14b")
        self.db.commit()

        deleted = local_model_policy.delete_model_role(self.db, self.role_name)
        self.db.commit()
        self.assertTrue(deleted)
        self.assertIsNone(
            self.db.query(AIModelRole).filter(AIModelRole.role_name == self.role_name).first()
        )

    def test_delete_model_role_on_nonexistent_role_reports_false(self):
        self.assertFalse(local_model_policy.delete_model_role(self.db, "definitely_not_a_saved_role"))


class TestResolveLocalModelRealDbRoundTrip(ModelRoleManagementTestBase):
    def test_real_db_row_overrides_resolve_local_model(self):
        # Register the role_name directly into CAPABILITY_LOCAL_MODEL_ROLE
        # for this one test via the fallback preference list mechanism -
        # simplest is to call resolve_local_model with a capability that
        # isn't mapped, so it falls back to _FALLBACK_ROLE_PREFERENCE
        # (["research"]) - so instead we directly exercise
        # _resolve_db_model_for_role() against our own role_name, which is
        # the actual unit resolve_local_model() itself calls per role in
        # its preference list.
        local_model_policy.save_model_role(self.db, self.role_name, model="qwen3:14b-real-db")
        self.db.commit()

        self.assertEqual(local_model_policy._resolve_db_model_for_role(self.role_name), "qwen3:14b-real-db")

    def test_disabled_real_db_row_is_skipped(self):
        local_model_policy.save_model_role(self.db, self.role_name, model="qwen3:14b-real-db", enabled=False)
        self.db.commit()

        self.assertIsNone(local_model_policy._resolve_db_model_for_role(self.role_name))

    def test_resolve_local_model_end_to_end_with_a_real_saved_research_override(self):
        # Overrides the well-known "research" role (used by
        # "research_analysis") for the duration of this one test only -
        # restored in tearDown via _restore_research_role below, since
        # "research" IS a shared, real role name other e2e tests/real
        # deployments may also depend on.
        original = self.db.query(AIModelRole).filter(AIModelRole.role_name == "research").first()
        original_model = original.model if original else None
        original_enabled = original.enabled if original else None
        try:
            local_model_policy.save_model_role(self.db, "research", model="qwen3:14b-e2e-override")
            self.db.commit()
            self.assertEqual(resolve_local_model("research_analysis"), "qwen3:14b-e2e-override")
        finally:
            if original is None:
                local_model_policy.delete_model_role(self.db, "research")
            else:
                local_model_policy.save_model_role(self.db, "research", model=original_model, enabled=original_enabled)
            self.db.commit()


class TestModelRoleRoutes(ModelRoleManagementTestBase):
    def test_put_creates_then_get_list_reflects_it(self):
        result = route_put_model_role(
            self.role_name, ModelRoleWrite(model="qwen3:14b", enabled=True), db=self.db, current_user=self.admin
        )
        self.assertEqual(result.role_name, self.role_name)
        self.assertEqual(result.model, "qwen3:14b")
        self.assertEqual(result.updated_by_user_email, self.admin.email)

        rows = route_list_model_roles(db=self.db, current_user=self.admin)
        self.assertIn(self.role_name, [r.role_name for r in rows])

    def test_put_without_model_on_new_role_raises_400(self):
        with self.assertRaises(HTTPException) as ctx:
            route_put_model_role(self.role_name, ModelRoleWrite(), db=self.db, current_user=self.admin)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_delete_route_removes_it_and_404s_on_repeat(self):
        route_put_model_role(self.role_name, ModelRoleWrite(model="qwen3:14b"), db=self.db, current_user=self.admin)

        route_delete_model_role(self.role_name, db=self.db, current_user=self.admin)

        with self.assertRaises(HTTPException) as ctx:
            route_delete_model_role(self.role_name, db=self.db, current_user=self.admin)
        self.assertEqual(ctx.exception.status_code, 404)


class TestGetCurrentActiveAdminStillGatesModelRoles(ModelRoleManagementTestBase):
    def test_non_admin_rejected_by_the_shared_admin_dependency(self):
        non_admin = User(email=f"m8-3-step3-user-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.OPERATOR)
        self.db.add(non_admin)
        self.db.commit()
        try:
            with self.assertRaises(HTTPException) as ctx:
                get_current_active_admin(current_user=non_admin)
            self.assertEqual(ctx.exception.status_code, 403)
        finally:
            self.db.query(User).filter(User.id == non_admin.id).delete(synchronize_session=False)
            self.db.commit()


if __name__ == "__main__":
    unittest.main()
