"""
M8.2 (AI Gateway Backend Integration) - real-DB coverage for
app.ai_gateway.ui_query. Same conventions as test_mailbox_brief_e2e.py:
direct function calls against a real SessionLocal, explicit
child-then-parent teardown. Requires a real database connection - not
runnable in a sandbox with no Docker/Postgres access. Only
py_compile-checked in the authoring sandbox; run for real via
verify_m8_2_ai_gateway_backend.sh, in Docker.

Covers: per-user isolation (Track A discipline - a second user's
AIRequestLog rows must never appear in this user's Activity/Approvals/
Overview), Overview aggregation, Activity ordering + limit, Approvals'
error_type filter, and Settings reflecting real app.core.config.settings
values. list_providers()/get_provider()/list_routing_decisions() need no
DB rows (pure registry/router reads) and are covered separately by
tests/test_local_model_policy_pure.py plus this file's
TestProviderAndRoutingReads (DB session still required only because
importing app.ai_gateway.ui_query needs sqlalchemy-backed models at
import time).

Run standalone with:
    python -m unittest tests.test_ai_gateway_ui_query_e2e
"""
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal

from app.ai_gateway import ui_query
from app.ai_gateway.providers.registry import PROVIDER_CLIENT_REGISTRY
from app.models.ai_request_log import AIRequestLog
from app.models.company_profile import CompanyProfile
from app.models.enums import UserRole
from app.models.user import User


class AIGatewayUIQueryTestBase(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.user_a = User(email=f"m82-a-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.user_b = User(email=f"m82-b-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add_all([self.user_a, self.user_b])
        self.db.flush()

        self.profile_a = CompanyProfile(owner_user_id=self.user_a.id, name="M8.2 Test Co A")
        self.profile_b = CompanyProfile(owner_user_id=self.user_b.id, name="M8.2 Test Co B")
        self.db.add_all([self.profile_a, self.profile_b])
        self.db.commit()

        self._log_ids: list[uuid.UUID] = []

    def tearDown(self):
        self.db.query(AIRequestLog).filter(AIRequestLog.id.in_(self._log_ids)).delete(synchronize_session=False)
        self.db.commit()
        self.db.query(CompanyProfile).filter(CompanyProfile.id.in_([self.profile_a.id, self.profile_b.id])).delete(
            synchronize_session=False
        )
        self.db.query(User).filter(User.id.in_([self.user_a.id, self.user_b.id])).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def _add_log(self, *, company_profile_id=None, **overrides) -> AIRequestLog:
        defaults = dict(
            occurred_at=datetime.now(timezone.utc),
            capability="research_analysis",
            provider_key="claude",
            model="claude-opus-4-5",
            tier="premium",
            duration_ms=250.0,
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.01,
            success=True,
            company_profile_id=company_profile_id,
        )
        defaults.update(overrides)
        entry = AIRequestLog(**defaults)
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        self._log_ids.append(entry.id)
        return entry


class TestPerUserIsolation(AIGatewayUIQueryTestBase):
    def test_activity_excludes_other_users_rows(self):
        self._add_log(company_profile_id=self.profile_a.id)
        self._add_log(company_profile_id=self.profile_b.id)

        activity_a = ui_query.list_activity(self.db, self.user_a)
        self.assertEqual(len(activity_a), 1)
        self.assertEqual(activity_a[0].company_name, "M8.2 Test Co A")

    def test_activity_excludes_unattributed_rows(self):
        # company_profile_id=None - a capability that hasn't threaded
        # ownership context yet. Must never leak into ANY user's view.
        self._add_log(company_profile_id=None)
        self._add_log(company_profile_id=self.profile_a.id)

        activity_a = ui_query.list_activity(self.db, self.user_a)
        self.assertEqual(len(activity_a), 1)

    def test_user_with_no_companies_sees_empty_activity(self):
        lonely_user = User(email=f"m82-lonely-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(lonely_user)
        self.db.commit()
        try:
            self._add_log(company_profile_id=self.profile_a.id)
            self.assertEqual(ui_query.list_activity(self.db, lonely_user), [])
            self.assertEqual(ui_query.get_overview(self.db, lonely_user).requests_today, 0)
        finally:
            self.db.query(User).filter(User.id == lonely_user.id).delete()
            self.db.commit()


class TestActivity(AIGatewayUIQueryTestBase):
    def test_ordered_most_recent_first_and_respects_limit(self):
        older = self._add_log(
            company_profile_id=self.profile_a.id, occurred_at=datetime.now(timezone.utc) - timedelta(hours=2)
        )
        newer = self._add_log(company_profile_id=self.profile_a.id)

        activity = ui_query.list_activity(self.db, self.user_a)
        self.assertEqual([e.id for e in activity], [newer.id, older.id])

        limited = ui_query.list_activity(self.db, self.user_a, limit=1)
        self.assertEqual(len(limited), 1)
        self.assertEqual(limited[0].id, newer.id)

    def test_premium_approval_required_row_maps_to_waiting_status(self):
        self._add_log(
            company_profile_id=self.profile_a.id,
            success=False,
            error_type="PremiumApprovalRequiredError",
            provider_key=None,
        )
        activity = ui_query.list_activity(self.db, self.user_a)
        self.assertEqual(activity[0].status, "waiting")

    def test_failed_row_maps_to_failed_status(self):
        self._add_log(company_profile_id=self.profile_a.id, success=False, error_type="ProviderUnavailableError")
        activity = ui_query.list_activity(self.db, self.user_a)
        self.assertEqual(activity[0].status, "failed")


class TestApprovals(AIGatewayUIQueryTestBase):
    def test_only_premium_approval_rows_returned(self):
        self._add_log(company_profile_id=self.profile_a.id, success=True)  # not an approval event
        self._add_log(
            company_profile_id=self.profile_a.id,
            success=False,
            error_type="PremiumApprovalRequiredError",
            provider_key=None,
            cost_usd=0.05,
        )
        approvals = ui_query.list_approvals(self.db, self.user_a)
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0].estimated_cost_usd, 0.05)
        self.assertGreaterEqual(approvals[0].waiting_minutes, 0.0)


class TestOverview(AIGatewayUIQueryTestBase):
    def test_aggregates_cost_and_success_rate(self):
        self._add_log(company_profile_id=self.profile_a.id, success=True, cost_usd=0.02, tier="premium")
        self._add_log(company_profile_id=self.profile_a.id, success=False, cost_usd=0.0, tier="local")

        overview = ui_query.get_overview(self.db, self.user_a)
        self.assertEqual(overview.requests_today, 2)
        self.assertEqual(overview.success_rate_pct, 50.0)
        self.assertAlmostEqual(overview.estimated_cost_today_usd, 0.02)
        self.assertEqual(overview.premium_requests_today, 1)
        self.assertIn(overview.gateway_health, ("healthy", "down"))
        self.assertGreaterEqual(overview.total_providers, overview.active_providers)


class TestProviderAndRoutingReads(AIGatewayUIQueryTestBase):
    def test_list_providers_covers_full_registry(self):
        providers = ui_query.list_providers(self.db)
        self.assertEqual({p.key for p in providers}, set(PROVIDER_CLIENT_REGISTRY.keys()))
        for p in providers:
            self.assertIn(p.status, ("connected", "not_configured"))
            self.assertIn(p.tier, ("local", "free", "premium"))

    def test_get_provider_unknown_key_returns_none(self):
        self.assertIsNone(ui_query.get_provider(self.db, "not_a_real_provider"))

    def test_routing_decisions_cover_live_capabilities(self):
        decisions = ui_query.list_routing_decisions()
        self.assertEqual(len(decisions), 2)
        for decision in decisions:
            self.assertGreater(len(decision.nodes), 0)
            self.assertIn(decision.outcome, ("success", "waiting", "failed"))


class TestProviderCapabilities(AIGatewayUIQueryTestBase):
    """M8.3 Step 5 (Provider Capability Viewer). list_provider_capabilities()
    is a pure registry read (no AIRequestLog rows involved) - grouped here
    rather than in the pure test suite only because importing
    app.ai_gateway.ui_query itself needs sqlalchemy-backed models at import
    time, same rationale TestProviderAndRoutingReads above already states
    for list_providers()/list_routing_decisions()."""

    def test_covers_full_provider_registry(self):
        entries = ui_query.list_provider_capabilities()
        self.assertEqual({e.provider_key for e in entries}, set(PROVIDER_CLIENT_REGISTRY.keys()))

    def test_every_entry_has_a_valid_tier_and_label(self):
        entries = ui_query.list_provider_capabilities()
        for e in entries:
            self.assertIn(e.tier, ("local", "free", "premium"))
            self.assertTrue(e.label)

    def test_no_registered_overrides_means_no_entry_reports_a_model_override(self):
        # Today's true state: _CAPABILITY_OVERRIDES (capabilities.py) has
        # zero real entries registered anywhere in the codebase, so every
        # provider's effective capabilities must equal its provider-level
        # default - has_model_override must be False and overridden_fields
        # empty for all of them. If this ever fails, it means a real
        # per-model override got registered somewhere - update this test
        # deliberately rather than treating it as a regression.
        entries = ui_query.list_provider_capabilities()
        for e in entries:
            self.assertFalse(e.has_model_override, msg=f"{e.provider_key} unexpectedly reports a model override")
            self.assertEqual(e.overridden_fields, [])
            self.assertEqual(e.provider_level, e.effective)

    def test_provider_level_matches_registry_classvar(self):
        entries = {e.provider_key: e for e in ui_query.list_provider_capabilities()}
        for key, cls in PROVIDER_CLIENT_REGISTRY.items():
            entry = entries[key]
            self.assertEqual(entry.provider_level.structured_output, cls.capabilities.structured_output)
            self.assertEqual(entry.provider_level.tool_calling, cls.capabilities.tool_calling)
            self.assertEqual(entry.provider_level.vision, cls.capabilities.vision)
            self.assertEqual(entry.provider_level.embeddings, cls.capabilities.embeddings)
            self.assertEqual(entry.provider_level.streaming, cls.capabilities.streaming)
            self.assertEqual(entry.provider_level.reasoning_support, cls.capabilities.reasoning_support)


class TestSettings(AIGatewayUIQueryTestBase):
    def test_reflects_real_config_values(self):
        from app.core.config import settings as real_settings

        result = ui_query.get_settings()
        self.assertEqual(result.ai_mode, real_settings.AI_MODE)
        self.assertEqual(result.require_premium_approval, real_settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL)
        self.assertIn("research", result.local_model_roles)
        self.assertIn("writing", result.local_model_roles)
        self.assertIn("research_analysis", result.capability_local_model_role)


if __name__ == "__main__":
    unittest.main()
