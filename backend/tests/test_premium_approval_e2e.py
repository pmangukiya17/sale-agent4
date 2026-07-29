"""
M8.3 (AI Gateway Management & Control, Step 7 - Premium Approval UI) -
real-DB / real-route coverage. Same conventions as
test_provider_management_e2e.py (Step 2's own e2e file) and
test_model_role_management_e2e.py (Step 3's) - route functions are called
directly (not through FastAPI's routing layer/TestClient), passing an
already-resolved `current_user`/`db` straight in; `Depends(get_current_active_admin)`
actually 403ing an unauthenticated HTTP request is framework-level and
already proven by the pre-existing POST /auth/register precedent (see
those two files' own docstrings for the full reasoning) - what's new and
worth testing here is each route/service function's own logic once a
current_user is already resolved.

Requires a real database connection - not runnable in this authoring
sandbox (no Docker/Postgres access, and pydantic/sqlalchemy aren't even
importable here). Only py_compile-checked in the authoring sandbox; run
for real via verify_m8_3_step7_premium_approval.sh, in Docker.

Covers:
  - app.ai_gateway.premium_preauthorization's service layer against a real
    DB: has_live_preauthorization() (live/expired/wrong-capability/wrong-
    company/None-company), latest_decision_for() (most-recent-by-decided_at,
    including after a later rejection supersedes an earlier approval),
    grant_preauthorization() (writes a NEW row every call, never updates;
    sets expires_at = decided_at + settings.AI_GATEWAY_PREMIUM_PREAUTH_MINUTES
    for an approval, leaves it None for a rejection; raises ValueError for
    an invalid decision string), list_preauthorization_history() (scoping
    by company_profile_ids, most-recent-first, empty-list short circuit).
  - app.ai_gateway.premium_approval_resolver.SQLAlchemyPremiumApprovalResolver
    against a real DB (the one branch test_premium_approval_resolver_pure.py
    cannot reach without Docker: a valid company_profile_id that actually
    resolves a live/expired grant).
  - app.ai_gateway.ui_query's Step 7 additions: _approval_status_for() via
    list_approvals()'s own `status` field (pending/approved/rejected, and
    an EXPIRED approval correctly reading as pending again - see that
    function's own docstring), get_approval_request_log() (happy path,
    wrong error_type, unowned company, unknown id -> all None),
    to_premium_preauthorization_read() (field mapping), and
    list_approval_history() (scoping + ordering).
  - The three new routes in app/api/routes/ai_gateway.py: POST
    .../approve, POST .../reject (each 404s for an unknown/wrong-type/
    unowned approval_id, writes exactly one new AIPremiumPreauthorization
    row, and is admin-gated the same way get_current_active_admin() is
    already proven to gate Provider Management/Model Role Management -
    see TestGetCurrentActiveAdmin below, reusing that exact precedent
    rather than re-deriving it), and GET .../history (reflects both routes'
    writes, most-recent-first, scoped to the caller's own companies).

Run standalone with:
    python -m unittest tests.test_premium_approval_e2e
"""
import unittest
import uuid
from datetime import datetime, timedelta, timezone

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal

from app.ai_gateway import premium_preauthorization, ui_query
from app.ai_gateway.premium_approval_resolver import SQLAlchemyPremiumApprovalResolver
from app.api.deps import get_current_active_admin
from app.api.routes.ai_gateway import (
    approve_premium_request as route_approve_premium_request,
    list_approval_history as route_list_approval_history,
    reject_premium_request as route_reject_premium_request,
)
from app.models.ai_premium_preauthorization import AIPremiumPreauthorization
from app.models.ai_request_log import AIRequestLog
from app.models.company_profile import CompanyProfile
from app.models.enums import UserRole
from app.models.user import User
from fastapi import HTTPException

_PREMIUM_APPROVAL_ERROR_TYPE = "PremiumApprovalRequiredError"
_CAPABILITY = "test_m8_3_step7_capability"


class PremiumApprovalTestBase(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.admin = User(email=f"m8-3-step7-admin-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.non_admin = User(email=f"m8-3-step7-user-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.OPERATOR)
        self.db.add_all([self.admin, self.non_admin])
        self.db.flush()

        self.profile_a = CompanyProfile(owner_user_id=self.admin.id, name="M8.3 Step 7 Test Co A")
        self.profile_b = CompanyProfile(owner_user_id=self.admin.id, name="M8.3 Step 7 Test Co B")
        self.db.add_all([self.profile_a, self.profile_b])
        self.db.commit()

        self._grant_ids: list[uuid.UUID] = []
        self._log_ids: list[uuid.UUID] = []

    def tearDown(self):
        self.db.query(AIPremiumPreauthorization).filter(AIPremiumPreauthorization.id.in_(self._grant_ids)).delete(
            synchronize_session=False
        )
        self.db.query(AIRequestLog).filter(AIRequestLog.id.in_(self._log_ids)).delete(synchronize_session=False)
        self.db.commit()
        self.db.query(CompanyProfile).filter(CompanyProfile.id.in_([self.profile_a.id, self.profile_b.id])).delete(
            synchronize_session=False
        )
        self.db.query(User).filter(User.id.in_([self.admin.id, self.non_admin.id])).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def _grant(self, *, company_profile_id, capability=_CAPABILITY, decision, decided_at=None, expires_at=None) -> AIPremiumPreauthorization:
        """Writes a grant row directly (bypassing grant_preauthorization()'s
        own expires_at computation) so tests can construct already-expired
        or precisely-timed rows - grant_preauthorization() itself is
        exercised separately, at real time, by TestGrantPreauthorization
        below."""
        row = AIPremiumPreauthorization(
            company_profile_id=company_profile_id,
            capability=capability,
            decision=decision,
            decided_by_user_id=self.admin.id,
            decided_at=decided_at or datetime.now(timezone.utc),
            expires_at=expires_at,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        self._grant_ids.append(row.id)
        return row

    def _add_approval_log(self, *, company_profile_id, capability=_CAPABILITY, **overrides) -> AIRequestLog:
        defaults = dict(
            occurred_at=datetime.now(timezone.utc),
            capability=capability,
            provider_key=None,
            model="fake-premium-model",
            tier="premium",
            duration_ms=0.0,
            prompt_tokens=None,
            completion_tokens=None,
            cost_usd=0.05,
            success=False,
            error_type=_PREMIUM_APPROVAL_ERROR_TYPE,
            company_profile_id=company_profile_id,
        )
        defaults.update(overrides)
        entry = AIRequestLog(**defaults)
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        self._log_ids.append(entry.id)
        return entry


class TestGetCurrentActiveAdmin(PremiumApprovalTestBase):
    """Same precedent test_provider_management_e2e.py's own
    TestGetCurrentActiveAdmin class already establishes - repeated here
    (not skipped) so this file stands alone as proof Step 7's own routes
    sit behind the identical, already-verified admin boundary, per the
    CEO's explicit "keep this consistent" decision (2026-07-29)."""

    def test_admin_passes_through_unchanged(self):
        self.assertIs(get_current_active_admin(current_user=self.admin), self.admin)

    def test_non_admin_raises_403(self):
        with self.assertRaises(HTTPException) as ctx:
            get_current_active_admin(current_user=self.non_admin)
        self.assertEqual(ctx.exception.status_code, 403)


class TestHasLivePreauthorization(PremiumApprovalTestBase):
    def test_no_grant_returns_false(self):
        self.assertFalse(
            premium_preauthorization.has_live_preauthorization(
                self.db, company_profile_id=self.profile_a.id, capability=_CAPABILITY
            )
        )

    def test_none_company_profile_id_returns_false(self):
        self.assertFalse(
            premium_preauthorization.has_live_preauthorization(self.db, company_profile_id=None, capability=_CAPABILITY)
        )

    def test_live_approval_returns_true(self):
        self._grant(
            company_profile_id=self.profile_a.id,
            decision=premium_preauthorization.DECISION_APPROVED,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        self.assertTrue(
            premium_preauthorization.has_live_preauthorization(
                self.db, company_profile_id=self.profile_a.id, capability=_CAPABILITY
            )
        )

    def test_expired_approval_returns_false(self):
        self._grant(
            company_profile_id=self.profile_a.id,
            decision=premium_preauthorization.DECISION_APPROVED,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        self.assertFalse(
            premium_preauthorization.has_live_preauthorization(
                self.db, company_profile_id=self.profile_a.id, capability=_CAPABILITY
            )
        )

    def test_rejected_grant_never_counts_as_live(self):
        self._grant(company_profile_id=self.profile_a.id, decision=premium_preauthorization.DECISION_REJECTED)
        self.assertFalse(
            premium_preauthorization.has_live_preauthorization(
                self.db, company_profile_id=self.profile_a.id, capability=_CAPABILITY
            )
        )

    def test_scoped_to_exact_capability(self):
        self._grant(
            company_profile_id=self.profile_a.id,
            capability="a_different_capability",
            decision=premium_preauthorization.DECISION_APPROVED,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        self.assertFalse(
            premium_preauthorization.has_live_preauthorization(
                self.db, company_profile_id=self.profile_a.id, capability=_CAPABILITY
            )
        )

    def test_scoped_to_exact_company(self):
        self._grant(
            company_profile_id=self.profile_a.id,
            decision=premium_preauthorization.DECISION_APPROVED,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        self.assertFalse(
            premium_preauthorization.has_live_preauthorization(
                self.db, company_profile_id=self.profile_b.id, capability=_CAPABILITY
            )
        )


class TestSQLAlchemyResolverRealDb(PremiumApprovalTestBase):
    """The one branch test_premium_approval_resolver_pure.py cannot reach
    without Docker - a valid, real company_profile_id that actually
    resolves through to has_live_preauthorization()."""

    def setUp(self):
        super().setUp()
        self.resolver = SQLAlchemyPremiumApprovalResolver()

    def test_live_grant_resolves_true(self):
        self._grant(
            company_profile_id=self.profile_a.id,
            decision=premium_preauthorization.DECISION_APPROVED,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        self.assertTrue(
            self.resolver.is_preauthorized(company_profile_id=str(self.profile_a.id), capability=_CAPABILITY)
        )

    def test_no_grant_resolves_false(self):
        self.assertFalse(
            self.resolver.is_preauthorized(company_profile_id=str(self.profile_a.id), capability=_CAPABILITY)
        )

    def test_expired_grant_resolves_false(self):
        self._grant(
            company_profile_id=self.profile_a.id,
            decision=premium_preauthorization.DECISION_APPROVED,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        self.assertFalse(
            self.resolver.is_preauthorized(company_profile_id=str(self.profile_a.id), capability=_CAPABILITY)
        )


class TestLatestDecisionFor(PremiumApprovalTestBase):
    def test_no_decisions_returns_none(self):
        self.assertIsNone(
            premium_preauthorization.latest_decision_for(self.db, company_profile_id=self.profile_a.id, capability=_CAPABILITY)
        )

    def test_rejection_after_approval_is_the_latest(self):
        approval = self._grant(
            company_profile_id=self.profile_a.id,
            decision=premium_preauthorization.DECISION_APPROVED,
            decided_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=110),
        )
        rejection = self._grant(company_profile_id=self.profile_a.id, decision=premium_preauthorization.DECISION_REJECTED)

        latest = premium_preauthorization.latest_decision_for(self.db, company_profile_id=self.profile_a.id, capability=_CAPABILITY)
        self.assertEqual(latest.id, rejection.id)
        self.assertNotEqual(latest.id, approval.id)


class TestGrantPreauthorization(PremiumApprovalTestBase):
    def test_approval_sets_expires_at_using_configured_window(self):
        from app.core.config import settings

        before = datetime.now(timezone.utc)
        grant = premium_preauthorization.grant_preauthorization(
            self.db,
            company_profile_id=self.profile_a.id,
            capability=_CAPABILITY,
            decision=premium_preauthorization.DECISION_APPROVED,
            decided_by_user_id=self.admin.id,
        )
        self._grant_ids.append(grant.id)

        self.assertIsNotNone(grant.expires_at)
        expected = before + timedelta(minutes=settings.AI_GATEWAY_PREMIUM_PREAUTH_MINUTES)
        # Allow a small tolerance for real wall-clock time elapsed during
        # the call itself.
        self.assertLess(abs((grant.expires_at - expected).total_seconds()), 5)

    def test_rejection_leaves_expires_at_none(self):
        grant = premium_preauthorization.grant_preauthorization(
            self.db,
            company_profile_id=self.profile_a.id,
            capability=_CAPABILITY,
            decision=premium_preauthorization.DECISION_REJECTED,
            decided_by_user_id=self.admin.id,
        )
        self._grant_ids.append(grant.id)
        self.assertIsNone(grant.expires_at)

    def test_invalid_decision_raises_value_error(self):
        with self.assertRaises(ValueError):
            premium_preauthorization.grant_preauthorization(
                self.db,
                company_profile_id=self.profile_a.id,
                capability=_CAPABILITY,
                decision="maybe",
                decided_by_user_id=self.admin.id,
            )

    def test_each_call_writes_a_new_row_never_updates(self):
        first = premium_preauthorization.grant_preauthorization(
            self.db,
            company_profile_id=self.profile_a.id,
            capability=_CAPABILITY,
            decision=premium_preauthorization.DECISION_APPROVED,
            decided_by_user_id=self.admin.id,
        )
        second = premium_preauthorization.grant_preauthorization(
            self.db,
            company_profile_id=self.profile_a.id,
            capability=_CAPABILITY,
            decision=premium_preauthorization.DECISION_REJECTED,
            decided_by_user_id=self.admin.id,
        )
        self._grant_ids.extend([first.id, second.id])
        self.assertNotEqual(first.id, second.id)

        history = premium_preauthorization.list_preauthorization_history(self.db, company_profile_ids=[self.profile_a.id])
        self.assertEqual({row.id for row in history}, {first.id, second.id})


class TestListPreauthorizationHistory(PremiumApprovalTestBase):
    def test_empty_company_list_returns_empty(self):
        self.assertEqual(premium_preauthorization.list_preauthorization_history(self.db, company_profile_ids=[]), [])

    def test_scoped_to_given_companies_only(self):
        a = self._grant(company_profile_id=self.profile_a.id, decision=premium_preauthorization.DECISION_REJECTED)
        self._grant(company_profile_id=self.profile_b.id, decision=premium_preauthorization.DECISION_REJECTED)

        history = premium_preauthorization.list_preauthorization_history(self.db, company_profile_ids=[self.profile_a.id])
        self.assertEqual([row.id for row in history], [a.id])

    def test_most_recent_first(self):
        older = self._grant(
            company_profile_id=self.profile_a.id,
            decision=premium_preauthorization.DECISION_REJECTED,
            decided_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        newer = self._grant(company_profile_id=self.profile_a.id, decision=premium_preauthorization.DECISION_REJECTED)

        history = premium_preauthorization.list_preauthorization_history(self.db, company_profile_ids=[self.profile_a.id])
        self.assertEqual([row.id for row in history], [newer.id, older.id])


class TestApprovalStatusInListApprovals(PremiumApprovalTestBase):
    """ui_query.list_approvals()'s new `status` field, via
    _approval_status_for() - the CEO-reviewed pending/approved/rejected
    semantics (see ApprovalRequestRead.status's own docstring)."""

    def test_no_decision_yet_is_pending(self):
        self._add_approval_log(company_profile_id=self.profile_a.id)
        approvals = ui_query.list_approvals(self.db, self.admin)
        self.assertEqual(approvals[0].status, "pending")

    def test_live_approval_is_approved(self):
        self._add_approval_log(company_profile_id=self.profile_a.id)
        self._grant(
            company_profile_id=self.profile_a.id,
            decision=premium_preauthorization.DECISION_APPROVED,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        approvals = ui_query.list_approvals(self.db, self.admin)
        self.assertEqual(approvals[0].status, "approved")

    def test_rejected_decision_is_rejected(self):
        self._add_approval_log(company_profile_id=self.profile_a.id)
        self._grant(company_profile_id=self.profile_a.id, decision=premium_preauthorization.DECISION_REJECTED)
        approvals = ui_query.list_approvals(self.db, self.admin)
        self.assertEqual(approvals[0].status, "rejected")

    def test_expired_approval_reverts_to_pending(self):
        self._add_approval_log(company_profile_id=self.profile_a.id)
        self._grant(
            company_profile_id=self.profile_a.id,
            decision=premium_preauthorization.DECISION_APPROVED,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        approvals = ui_query.list_approvals(self.db, self.admin)
        self.assertEqual(approvals[0].status, "pending")


class TestGetApprovalRequestLog(PremiumApprovalTestBase):
    def test_unknown_id_returns_none(self):
        self.assertIsNone(ui_query.get_approval_request_log(self.db, self.admin, uuid.uuid4()))

    def test_wrong_error_type_returns_none(self):
        row = self._add_approval_log(company_profile_id=self.profile_a.id, error_type="ProviderUnavailableError", success=False)
        self.assertIsNone(ui_query.get_approval_request_log(self.db, self.admin, row.id))

    def test_unowned_company_returns_none(self):
        stranger = User(email=f"m8-3-step7-stranger-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(stranger)
        self.db.commit()
        try:
            row = self._add_approval_log(company_profile_id=self.profile_a.id)
            self.assertIsNone(ui_query.get_approval_request_log(self.db, stranger, row.id))
        finally:
            self.db.query(User).filter(User.id == stranger.id).delete()
            self.db.commit()

    def test_unattributed_row_returns_none(self):
        row = self._add_approval_log(company_profile_id=None)
        self.assertIsNone(ui_query.get_approval_request_log(self.db, self.admin, row.id))

    def test_happy_path_returns_the_row(self):
        row = self._add_approval_log(company_profile_id=self.profile_a.id)
        found = ui_query.get_approval_request_log(self.db, self.admin, row.id)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, row.id)


class TestApproveRejectRoutes(PremiumApprovalTestBase):
    def test_approve_unknown_id_404(self):
        with self.assertRaises(HTTPException) as ctx:
            route_approve_premium_request(uuid.uuid4(), db=self.db, current_user=self.admin)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_reject_unknown_id_404(self):
        with self.assertRaises(HTTPException) as ctx:
            route_reject_premium_request(uuid.uuid4(), db=self.db, current_user=self.admin)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_approve_writes_a_grant_and_returns_it(self):
        row = self._add_approval_log(company_profile_id=self.profile_a.id, cost_usd=0.07)

        result = route_approve_premium_request(row.id, db=self.db, current_user=self.admin)
        self._grant_ids.append(result.id)

        self.assertEqual(result.decision, premium_preauthorization.DECISION_APPROVED)
        self.assertIsNotNone(result.expires_at)
        self.assertEqual(result.company_name, "M8.3 Step 7 Test Co A")
        self.assertEqual(result.decided_by, self.admin.full_name or self.admin.email)
        self.assertAlmostEqual(result.source_estimated_cost_usd, 0.07)

        # The next attempt of this exact (company, capability) is now
        # pre-authorized - proves the route's write is actually load-
        # bearing for the gate, not just a cosmetic audit row.
        self.assertTrue(
            premium_preauthorization.has_live_preauthorization(
                self.db, company_profile_id=self.profile_a.id, capability=row.capability
            )
        )

    def test_reject_writes_a_grant_with_no_expiry(self):
        row = self._add_approval_log(company_profile_id=self.profile_a.id)

        result = route_reject_premium_request(row.id, db=self.db, current_user=self.admin)
        self._grant_ids.append(result.id)

        self.assertEqual(result.decision, premium_preauthorization.DECISION_REJECTED)
        self.assertIsNone(result.expires_at)
        self.assertFalse(
            premium_preauthorization.has_live_preauthorization(
                self.db, company_profile_id=self.profile_a.id, capability=row.capability
            )
        )

    def test_approve_then_reject_same_row_writes_two_rows(self):
        row = self._add_approval_log(company_profile_id=self.profile_a.id)

        approved = route_approve_premium_request(row.id, db=self.db, current_user=self.admin)
        rejected = route_reject_premium_request(row.id, db=self.db, current_user=self.admin)
        self._grant_ids.extend([approved.id, rejected.id])

        self.assertNotEqual(approved.id, rejected.id)


class TestApprovalHistoryRoute(PremiumApprovalTestBase):
    def test_reflects_approve_and_reject_most_recent_first(self):
        row_a = self._add_approval_log(company_profile_id=self.profile_a.id, capability=_CAPABILITY)
        row_b = self._add_approval_log(company_profile_id=self.profile_a.id, capability=f"{_CAPABILITY}_2")

        first = route_approve_premium_request(row_a.id, db=self.db, current_user=self.admin)
        second = route_reject_premium_request(row_b.id, db=self.db, current_user=self.admin)
        self._grant_ids.extend([first.id, second.id])

        history = route_list_approval_history(limit=100, db=self.db, current_user=self.admin)
        history_ids = [h.id for h in history]
        self.assertIn(first.id, history_ids)
        self.assertIn(second.id, history_ids)
        # Most-recent-first: the reject (written second) appears before
        # the approve (written first).
        self.assertLess(history_ids.index(second.id), history_ids.index(first.id))

    def test_empty_for_admin_with_no_companies(self):
        lonely_admin = User(email=f"m8-3-step7-lonely-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(lonely_admin)
        self.db.commit()
        try:
            self.assertEqual(route_list_approval_history(limit=100, db=self.db, current_user=lonely_admin), [])
        finally:
            self.db.query(User).filter(User.id == lonely_admin.id).delete()
            self.db.commit()


if __name__ == "__main__":
    unittest.main()
