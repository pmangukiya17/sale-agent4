"""
Real, DB-backed tests of connection_service.build_reconnect_authorize_url
- the Outlook Integration milestone's core fix (found during CEO-reported
live testing: outbound send was permanently failing with a Graph 403
because the draft-creation call needs Mail.ReadWrite, which was never
requested - see app/delivery/providers/outlook_provider.py's own
docstring for the full root cause).

This function had ZERO test coverage of any kind before this milestone.
The pure scope-union math it delegates to is covered in full, in
isolation, by tests/test_scope_utils.py (no database needed there - see
that module's own docstring). This file instead proves the function's
DB-facing behavior: it looks up a real ProviderConnection, calls the
REAL OutlookProvider/GmailProvider class (no monkeypatching - unlike
tests/test_sync_worker_cursor_contract.py, get_authorize_url is a pure,
deterministic URL builder with no network call, so there is no reason to
stub it), and returns a URL whose `scope` query parameter reflects the
provider's CURRENT send_scopes topped up correctly, plus read_scopes only
when explicitly requested.

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access (this sandbox has neither Docker nor a
working `sqlalchemy` import - see this project's own standing disclosure
elsewhere). Only tests/test_scope_utils.py was actually executed while
authoring this milestone; this file is py_compile-checked only until the
CEO runs it for real.

Run standalone with:
    python -m unittest tests.test_connection_service_reconnect_scopes
"""
import unittest
import uuid
from urllib.parse import parse_qs, urlparse

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.delivery.connection_service import ConnectionError_, build_reconnect_authorize_url
from app.delivery.providers.outlook_provider import OutlookProvider
from app.models.company_profile import CompanyProfile
from app.models.enums import ProviderConnectionStatus, UserRole
from app.models.provider_connection import ProviderConnection
from app.models.user import User


def _scope_set_from_authorize_url(url: str) -> set[str]:
    query = parse_qs(urlparse(url).query)
    return set(query["scope"][0].split())


class ReconnectScopeTestBase(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.user = User(email=f"outlook-integration-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()
        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="Outlook Integration Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.flush()
        self._connection_ids: list[uuid.UUID] = []

    def tearDown(self):
        for connection_id in self._connection_ids:
            self.db.query(ProviderConnection).filter(ProviderConnection.id == connection_id).delete()
        self.db.commit()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    def _make_connection(self, *, provider_key: str, scopes_granted: list[str] | None) -> ProviderConnection:
        connection = ProviderConnection(
            company_profile_id=self.company_profile.id,
            provider_key=provider_key,
            status=ProviderConnectionStatus.CONNECTED,
            scopes_granted=scopes_granted,
        )
        self.db.add(connection)
        self.db.commit()
        self._connection_ids.append(connection.id)
        return connection


class TestSendScopeTopUp(ReconnectScopeTestBase):
    """The core repair: an existing Outlook connection that was granted
    only the OLD, narrower send_scopes (no Mail.ReadWrite, from before
    this milestone's fix) must, on a plain Reconnect (include_read_scopes
    defaults to False), come back with a URL requesting the CURRENT
    baseline - i.e. it must self-heal without the caller needing to know
    a scope requirement changed."""

    def test_old_narrow_grant_is_topped_up_to_current_send_scopes(self):
        connection = self._make_connection(
            provider_key="outlook",
            scopes_granted=[
                "https://graph.microsoft.com/Mail.Send",
                "https://graph.microsoft.com/User.Read",
                "offline_access",
            ],
        )
        url = build_reconnect_authorize_url(self.db, connection.id)
        scopes = _scope_set_from_authorize_url(url)
        for required in OutlookProvider.send_scopes:
            self.assertIn(required, scopes, f"missing required baseline scope: {required}")

    def test_plain_reconnect_never_adds_read_scopes(self):
        connection = self._make_connection(provider_key="outlook", scopes_granted=["https://graph.microsoft.com/Mail.Send"])
        url = build_reconnect_authorize_url(self.db, connection.id)  # include_read_scopes defaults to False
        scopes = _scope_set_from_authorize_url(url)
        self.assertNotIn("https://graph.microsoft.com/Mail.Read", scopes)

    def test_connection_with_no_scopes_recorded_yet_gets_full_baseline(self):
        connection = self._make_connection(provider_key="outlook", scopes_granted=None)
        url = build_reconnect_authorize_url(self.db, connection.id)
        scopes = _scope_set_from_authorize_url(url)
        for required in OutlookProvider.send_scopes:
            self.assertIn(required, scopes)

    def test_already_fully_upgraded_connection_is_unaffected(self):
        # A connection that already reconnected once after this fix
        # shipped - re-reconnecting again must be a no-op on scope
        # content (still exactly the baseline, nothing lost, nothing
        # duplicated in a way that would change behavior).
        connection = self._make_connection(provider_key="outlook", scopes_granted=list(OutlookProvider.send_scopes))
        url = build_reconnect_authorize_url(self.db, connection.id)
        scopes = _scope_set_from_authorize_url(url)
        self.assertEqual(scopes, set(OutlookProvider.send_scopes))


class TestReadScopeOptIn(ReconnectScopeTestBase):
    """Requirement C: Mail.Read stays a separate, explicit opt-in - never
    granted as a side effect of the baseline top-up above."""

    def test_include_read_scopes_true_adds_mail_read_for_outlook(self):
        connection = self._make_connection(provider_key="outlook", scopes_granted=["https://graph.microsoft.com/Mail.Send"])
        url = build_reconnect_authorize_url(self.db, connection.id, include_read_scopes=True)
        scopes = _scope_set_from_authorize_url(url)
        for required in OutlookProvider.read_scopes:
            self.assertIn(required, scopes)
        # The send-scope baseline must STILL be present too - this is an
        # addition, not a replacement.
        for required in OutlookProvider.send_scopes:
            self.assertIn(required, scopes)

    def test_include_read_scopes_true_on_gmail_raises_cleanly(self):
        # Gmail has no IncrementalSyncCapable implementation at all today
        # - asking for read access on it must fail loudly, not silently
        # no-op and return a URL that looks like it granted something it
        # didn't.
        connection = self._make_connection(
            provider_key="gmail", scopes_granted=["https://www.googleapis.com/auth/gmail.send"]
        )
        with self.assertRaises(ConnectionError_):
            build_reconnect_authorize_url(self.db, connection.id, include_read_scopes=True)


if __name__ == "__main__":
    unittest.main()
