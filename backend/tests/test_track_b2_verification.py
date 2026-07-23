"""
Track B2 automated verification: the three areas
docs/architecture/comprehensive-verification-matrix.md's Group 3 (rows
35-37) listed as "No automated verification available" - reserved,
per the CEO's own sequencing, for a dedicated re-verification pass after
Track B1 rather than being folded into the general sweep. They correspond
to the three findings that drove the Track A architectural fixes:

    35. ProspectContact delete/archive behavior (RESTRICT-protected hard
        delete, archive/unarchive routes, default-hide-archived list
        filter) - app/api/routes/prospect_contacts.py, migration 0023/0024.
    36. Multi-business isolation - legacy Company/Contact tenant-scoping
        re-check - app/api/routes/companies.py, contacts.py. Per
        deferred-items-and-design-boundaries.md item 6, the decision was
        to leave this gap in place (staged for retirement, not lifecycle
        investment) rather than fix it - so this suite re-confirms the
        gap is exactly the accepted one, not that it's absent.
    37. Authentication registration flow - admin gate, bootstrap
        exception fires exactly once on a fresh DB, second registration
        without an admin token 403s - app/api/routes/auth.py.

Writing this file upgrades "Automated verification available" from No to
Yes for all three matrix rows; it does NOT by itself flip their Status
from Pending to Done - that still requires actually running this suite
against a real Postgres (see verify_track_b2.sh), which this sandbox
cannot do (no Docker/Postgres access, same standing limitation disclosed
throughout this project - see test_pilot_workflow_e2e.py's own
docstring for the identical caveat). Written and read carefully against
the real route/model code, but not executed here.

Run standalone with:
    python -m unittest tests.test_track_b2_verification
"""
import unittest
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from starlette.requests import Request

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode: SQLAlchemy needs
# every mapped class registered on the same Base before the first
# relationship() is resolved).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.api.deps import get_owned_company_profile
from app.api.routes.auth import register
from app.api.routes.companies import create_company, list_companies
from app.api.routes.contacts import create_contact, list_contacts
from app.api.routes.prospect_contacts import (
    archive_prospect_contact,
    delete_prospect_contact,
    list_prospect_contacts,
    unarchive_prospect_contact,
)
from app.core.security import create_access_token, hash_password
from app.models.company import Company
from app.models.company_profile import CompanyProfile
from app.models.contact import Contact
from app.models.enums import UserRole
from app.models.outreach_playbook import OutreachPlaybook
from app.models.outreach_request import OutreachRequest
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.user import User
from app.schemas.company import CompanyCreate
from app.schemas.contact import ContactCreate
from app.schemas.user import UserCreate


def _fake_request(bearer_token: str | None = None) -> Request:
    """A real Starlette Request carrying only what register() actually
    reads (request.headers.get("Authorization")) - not a mock, so header
    parsing goes through Starlette's real Headers class exactly as it
    would for a live HTTP request, just without booting a live server."""
    headers = []
    if bearer_token:
        headers.append((b"authorization", f"Bearer {bearer_token}".encode()))
    scope = {"type": "http", "headers": headers, "method": "POST", "path": "/api/v1/auth/register"}
    return Request(scope)


class TestProspectContactArchiveDeleteLifecycle(unittest.TestCase):
    """Row 35."""

    def setUp(self):
        self.db = SessionLocal()
        self.user = User(
            email=f"b2-pc-{uuid.uuid4()}@example.com", hashed_password=hash_password("x"), role=UserRole.ADMIN
        )
        self.db.add(self.user)
        self.db.flush()

        self.profile = CompanyProfile(owner_user_id=self.user.id, name="Track B2 PC Test Co")
        self.db.add(self.profile)
        self.db.flush()

        # first_discovered_at/last_seen_at are both nullable=False with no
        # column default (see app/models/prospect.py) - the real Discovery
        # pipeline always sets both to the same "fetched_at" timestamp at
        # creation (app/discovery/pipeline.py), which this fixture mirrors.
        # An earlier version of this fixture omitted both, which is a real
        # NOT NULL violation caught by an actual `verify_track_b2.sh` run
        # against Postgres, not something the pre-execution review here
        # (py_compile + manual signature cross-checks) could have caught -
        # constraint violations only surface at real insert time.
        now = datetime.now(timezone.utc)
        self.prospect = Prospect(
            company_profile_id=self.profile.id,
            name="Track B2 Test Prospect",
            first_discovered_at=now,
            last_seen_at=now,
        )
        self.db.add(self.prospect)
        self.db.flush()

        self.playbook = OutreachPlaybook(name="Track B2 Test Playbook", version=1, is_current=True)
        self.db.add(self.playbook)
        self.db.flush()

        # Two contacts: one gets real execution history attached (RESTRICT
        # must block its hard delete), the other stays untouched (hard
        # delete must still succeed there - RESTRICT should never mean "no
        # contact can ever be hard-deleted", only "not one with history").
        self.contact_with_history = ProspectContact(prospect_id=self.prospect.id, name="Has History")
        self.contact_without_history = ProspectContact(prospect_id=self.prospect.id, name="No History")
        self.db.add_all([self.contact_with_history, self.contact_without_history])
        self.db.flush()

        self.outreach_request = OutreachRequest(
            prospect_id=self.prospect.id,
            prospect_contact_id=self.contact_with_history.id,
            company_profile_id=self.profile.id,
            outreach_playbook_id=self.playbook.id,
            channel_key="email",
        )
        self.db.add(self.outreach_request)
        self.db.commit()

    def tearDown(self):
        self.db.rollback()  # discard any uncommitted state from a failed assertion mid-test
        self.db.query(OutreachRequest).filter(OutreachRequest.company_profile_id == self.profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()
        self.db.query(ProspectContact).filter(ProspectContact.prospect_id == self.prospect.id).delete(
            synchronize_session=False
        )
        self.db.query(Prospect).filter(Prospect.id == self.prospect.id).delete(synchronize_session=False)
        self.db.query(OutreachPlaybook).filter(OutreachPlaybook.id == self.playbook.id).delete(synchronize_session=False)
        self.db.commit()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.profile.id).delete(synchronize_session=False)
        self.db.query(User).filter(User.id == self.user.id).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def test_hard_delete_blocked_by_real_execution_history(self):
        with self.assertRaises(HTTPException) as ctx:
            delete_prospect_contact(
                prospect_id=self.prospect.id, contact_id=self.contact_with_history.id, profile=self.profile, db=self.db
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("outreach/delivery history", ctx.exception.detail)
        # And the row must genuinely still exist - RESTRICT should have
        # rolled the failed delete back, not partially applied it.
        self.assertIsNotNone(self.db.get(ProspectContact, self.contact_with_history.id))

    def test_hard_delete_succeeds_with_no_history(self):
        delete_prospect_contact(
            prospect_id=self.prospect.id, contact_id=self.contact_without_history.id, profile=self.profile, db=self.db
        )
        self.assertIsNone(self.db.get(ProspectContact, self.contact_without_history.id))

    def test_archive_unarchive_round_trip(self):
        archived = archive_prospect_contact(
            prospect_id=self.prospect.id,
            contact_id=self.contact_with_history.id,
            profile=self.profile,
            current_user=self.user,
            db=self.db,
        )
        self.assertTrue(archived.is_archived)
        self.assertIsNotNone(archived.archived_at)
        self.assertEqual(archived.archived_by_user_id, self.user.id)

        unarchived = unarchive_prospect_contact(
            prospect_id=self.prospect.id, contact_id=self.contact_with_history.id, profile=self.profile, db=self.db
        )
        self.assertFalse(unarchived.is_archived)
        self.assertIsNone(unarchived.archived_at)
        self.assertIsNone(unarchived.archived_by_user_id)

    def test_list_excludes_archived_by_default_and_includes_with_flag(self):
        archive_prospect_contact(
            prospect_id=self.prospect.id,
            contact_id=self.contact_with_history.id,
            profile=self.profile,
            current_user=self.user,
            db=self.db,
        )
        default_list = list_prospect_contacts(
            prospect_id=self.prospect.id, include_archived=False, profile=self.profile, db=self.db
        )
        self.assertNotIn(self.contact_with_history.id, [c.id for c in default_list])
        self.assertIn(self.contact_without_history.id, [c.id for c in default_list])

        full_list = list_prospect_contacts(
            prospect_id=self.prospect.id, include_archived=True, profile=self.profile, db=self.db
        )
        self.assertIn(self.contact_with_history.id, [c.id for c in full_list])


class TestAuthRegistrationAdminGate(unittest.TestCase):
    """Row 37 - the steady-state (non-bootstrap) behavior: every
    registration once at least one user exists requires a valid admin
    bearer token. Deliberately creates its own admin/operator fixtures up
    front so `is_bootstrap` is guaranteed False regardless of what else is
    in the shared `users` table - see TestAuthRegistrationBootstrapException
    below for the zero-users branch, which these fixtures would otherwise
    make impossible to exercise from the same setUp."""

    def setUp(self):
        self.db = SessionLocal()
        self.admin = User(
            email=f"b2-auth-admin-{uuid.uuid4()}@example.com", hashed_password=hash_password("x"), role=UserRole.ADMIN
        )
        self.operator = User(
            email=f"b2-auth-operator-{uuid.uuid4()}@example.com",
            hashed_password=hash_password("x"),
            role=UserRole.OPERATOR,
        )
        self.db.add_all([self.admin, self.operator])
        self.db.commit()
        # Captured as plain UUIDs, not read off self.admin/self.operator
        # again later - see tearDown's own comment for why touching those
        # ORM objects' attributes after a rollback/commit elsewhere is
        # exactly what caused the ObjectDeletedError this fixture used to
        # trigger.
        self.admin_id = self.admin.id
        self.operator_id = self.operator.id
        self.admin_token = create_access_token(subject=str(self.admin_id))
        self.operator_token = create_access_token(subject=str(self.operator_id))
        self._created_emails: list[str] = []

    def tearDown(self):
        self.db.rollback()
        if self._created_emails:
            self.db.query(User).filter(User.email.in_(self._created_emails)).delete(synchronize_session=False)
        # Filtered by the plain UUIDs captured in setUp, never by
        # self.admin.id/self.operator.id directly: `self.db.rollback()`
        # above expires every ORM object still attached to this session,
        # so reading an attribute off self.admin/self.operator here would
        # force SQLAlchemy to re-SELECT that row to refresh it. That's
        # exactly what broke test_registration_rejects_duplicate_email -
        # its email IS self.admin.email, so the `_created_emails` bulk
        # delete just above already removed self.admin's row from the DB;
        # accessing the (now rollback-expired) self.admin.id afterwards
        # raised ObjectDeletedError trying to refresh a row that's already
        # gone. Plain UUIDs captured before any commit/rollback can ever
        # expire them sidestep the whole problem.
        self.db.query(User).filter(User.id.in_([self.admin_id, self.operator_id])).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def _register(self, email: str, token: str | None):
        result = register(user_in=UserCreate(email=email, password="testpassword123"), request=_fake_request(token), db=self.db)
        # Only track emails that actually landed a new row - not every
        # email this test attempted to register with. The duplicate-email
        # test deliberately calls this with self.admin.email, which must
        # NEVER be queued for deletion here: it's self.admin's own fixture
        # row, not a row this call created (register() raises before
        # creating anything in that case, so this line is unreached for
        # that test, which is exactly the point).
        self._created_emails.append(email)
        return result

    def test_registration_without_token_is_403(self):
        with self.assertRaises(HTTPException) as ctx:
            self._register(f"b2-no-token-{uuid.uuid4()}@example.com", token=None)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_registration_with_non_admin_token_is_403(self):
        with self.assertRaises(HTTPException) as ctx:
            self._register(f"b2-operator-token-{uuid.uuid4()}@example.com", token=self.operator_token)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_registration_with_admin_token_succeeds_as_operator(self):
        email = f"b2-admin-token-{uuid.uuid4()}@example.com"
        new_user = self._register(email, token=self.admin_token)
        self.assertEqual(new_user.email, email)
        self.assertEqual(new_user.role, UserRole.OPERATOR)

    def test_registration_rejects_duplicate_email(self):
        with self.assertRaises(HTTPException) as ctx:
            self._register(self.admin.email, token=self.admin_token)
        self.assertEqual(ctx.exception.status_code, 400)


class TestAuthRegistrationBootstrapException(unittest.TestCase):
    """Row 37 - the bootstrap exception specifically: on a genuinely
    fresh database (zero rows in `users`), registration is open with no
    token, and the first account created is auto-granted ADMIN; the very
    next registration after that is no longer exempt.

    Deliberately does NOT create any user fixtures in setUp (unlike the
    class above) - doing so would make the emptiness precondition below
    impossible to satisfy from this test's own state. Instead it checks
    the real precondition (`db.query(User.id).first() is None`) and skips
    itself with an explicit message if the database isn't actually empty,
    rather than faking the condition or deleting real rows to force it -
    the same honesty discipline this project applies to every other
    "can't verify this here" disclosure. To exercise this for real, run
    this test alone against a throwaway database immediately after
    `alembic upgrade head`.

    A finding surfaced while writing this test, worth flagging explicitly
    rather than leaving implicit: in any normally-booted deployment, this
    branch is realistically UNREACHABLE via the live API. app.main's own
    `ensure_first_admin()` runs during FastAPI's startup lifespan, before
    the server accepts its first HTTP request, and seeds a real admin the
    moment `users` has zero rows - so by the time any client could call
    POST /auth/register, `is_bootstrap` is already False. This test only
    exercises the branch at all because it calls `register()` directly,
    bypassing `ensure_first_admin()` entirely - it is not, in practice, a
    path a real user would ever hit through the live API. That doesn't
    make the code wrong (it's a legitimate defensive fallback - e.g. if
    `ensure_first_admin()` is ever removed or a DB gets migrations applied
    without the app ever booting), but it does mean row 37's "bootstrap
    exception fires exactly once on a fresh DB" is really only checkable
    at this function-call level, never as observed live-API behavior."""

    def setUp(self):
        self.db = SessionLocal()
        self._created_emails: list[str] = []

    def tearDown(self):
        self.db.rollback()
        if self._created_emails:
            self.db.query(User).filter(User.email.in_(self._created_emails)).delete(synchronize_session=False)
            self.db.commit()
        self.db.close()

    def _skip_unless_empty(self):
        if self.db.query(User.id).first() is not None:
            self.skipTest(
                "users table is non-empty (expected for any already-booted deployment) - "
                "the bootstrap branch can only be safely exercised against a genuinely fresh "
                "database. Run this test alone against a throwaway DB right after "
                "`alembic upgrade head` to verify it for real."
            )

    def test_bootstrap_exception_grants_admin_on_empty_database(self):
        self._skip_unless_empty()
        email = f"b2-bootstrap-{uuid.uuid4()}@example.com"
        self._created_emails.append(email)
        new_user = register(user_in=UserCreate(email=email, password="testpassword123"), request=_fake_request(None), db=self.db)
        self.assertEqual(new_user.role, UserRole.ADMIN)

    def test_registration_immediately_after_bootstrap_requires_admin_token(self):
        self._skip_unless_empty()
        first_email = f"b2-bootstrap-first-{uuid.uuid4()}@example.com"
        self._created_emails.append(first_email)
        first_user = register(
            user_in=UserCreate(email=first_email, password="testpassword123"), request=_fake_request(None), db=self.db
        )
        self.assertEqual(first_user.role, UserRole.ADMIN)

        second_email = f"b2-bootstrap-second-{uuid.uuid4()}@example.com"
        self._created_emails.append(second_email)
        with self.assertRaises(HTTPException) as ctx:
            register(
                user_in=UserCreate(email=second_email, password="testpassword123"), request=_fake_request(None), db=self.db
            )
        self.assertEqual(ctx.exception.status_code, 403)


class TestLegacyCompanyContactKnownIsolationGap(unittest.TestCase):
    """Row 36 - re-confirms the ALREADY-ACCEPTED, documented tenant-
    isolation gap in the legacy Company/Contact models (see
    deferred-items-and-design-boundaries.md item 6: staged for
    retirement, not lifecycle investment - fixing isolation here was
    explicitly decided against, not overlooked). This suite exists to
    catch DRIFT, not to bless the gap:

      - if this test starts FAILING because Company/Contact suddenly
        became properly owner-scoped, that's good news - update this
        test (and the matrix/deferred-items docs) to match; don't just
        loosen the assertion to make it pass again.
      - if it fails because a REAL tenant-scoped route (e.g.
        get_owned_company_profile, which every Prospect-family endpoint
        depends on) stops isolating data between owners, that is a
        genuine regression - the final test below is what would catch
        it, proving the legacy gap stays contained to Company/Contact and
        never spreads into the boundary the rest of the platform actually
        relies on.
    """

    def setUp(self):
        self.db = SessionLocal()
        self.user_a = User(
            email=f"b2-legacy-a-{uuid.uuid4()}@example.com", hashed_password=hash_password("x"), role=UserRole.OPERATOR
        )
        self.user_b = User(
            email=f"b2-legacy-b-{uuid.uuid4()}@example.com", hashed_password=hash_password("x"), role=UserRole.OPERATOR
        )
        self.db.add_all([self.user_a, self.user_b])
        self.db.commit()

        self.company_a = create_company(CompanyCreate(name="B2 Legacy Co A"), db=self.db, current_user=self.user_a)
        self.contact_a = create_contact(
            ContactCreate(company_id=self.company_a.id, name="Contact A"), db=self.db, current_user=self.user_a
        )

        # A real, tenant-scoped fixture too, so the last test below can
        # prove the legacy gap doesn't leak into the actual boundary.
        self.profile_a = CompanyProfile(owner_user_id=self.user_a.id, name="B2 Real Profile A")
        self.db.add(self.profile_a)
        self.db.commit()

    def tearDown(self):
        self.db.rollback()
        self.db.query(Contact).filter(Contact.id == self.contact_a.id).delete(synchronize_session=False)
        self.db.query(Company).filter(Company.id == self.company_a.id).delete(synchronize_session=False)
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.profile_a.id).delete(synchronize_session=False)
        self.db.commit()
        self.db.query(User).filter(User.id.in_([self.user_a.id, self.user_b.id])).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def test_legacy_company_list_is_not_owner_scoped_known_gap(self):
        # user_b, a totally different account, can see user_a's legacy
        # Company row via the same plain list_companies() every user
        # shares - the documented gap, not a bug being newly discovered.
        visible_to_b = list_companies(skip=0, limit=200, db=self.db, current_user=self.user_b)
        self.assertIn(self.company_a.id, [c.id for c in visible_to_b])

    def test_legacy_contact_list_is_not_owner_scoped_known_gap(self):
        visible_to_b = list_contacts(company_id=None, skip=0, limit=200, db=self.db, current_user=self.user_b)
        self.assertIn(self.contact_a.id, [c.id for c in visible_to_b])

    def test_real_tenant_boundary_is_unaffected_by_the_legacy_gap(self):
        with self.assertRaises(HTTPException) as ctx:
            get_owned_company_profile(company_profile_id=self.profile_a.id, db=self.db, current_user=self.user_b)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
