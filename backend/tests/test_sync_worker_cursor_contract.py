"""
Real, DB-backed tests of sync_worker.sync_one_connection's actual
orchestration logic - not just the pure normalize.py mapping (see
tests/test_reply_intelligence_normalize.py) and not just raw schema
constraints (see tests/test_mailbox_sync_models.py). This module proves
the cursor/commit/dedup CONTRACT described in
docs/architecture/m6-reply-intelligence-plan.md's "Synchronization Cursor
Contract - as built" section actually holds, end to end, against a real
Postgres session.

A stub `IncrementalSyncCapable` provider stands in for OutlookProvider -
see tests/test_outlook_provider_sync.py for the Outlook-specific,
mocked-Graph-response tests that cover the adapter's own HTTP/parsing
logic instead. This module never makes an HTTP call and never needs live
Outlook credentials; `sync_worker.get_provider` and
`sync_worker.refresh_credential_if_needed` are monkeypatched for the
duration of each test so `sync_one_connection` runs its real DB-facing
logic (message persistence, dedup, cursor/state bookkeeping) against a
fully deterministic, in-memory fake instead of a real provider/credential
round-trip.

"Cursor persisted only after commit" is tested from the observable side
(what a caller could actually assert, without literally killing the
process mid-transaction): `test_failed_tick_does_not_lose_previously_
synced_messages_or_corrupt_cursor` proves that a tick which fails AFTER a
prior tick already committed successfully (a) does not roll back that
prior tick's messages, and (b) leaves the cursor at its last successfully
-committed value, not silently advanced past a failure. That is the
externally-observable consequence of the code committing messages before
advancing the cursor - see sync_worker.py's own docstring for the code-
level ordering this behavior follows from.

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_sync_worker_cursor_contract
"""
import unittest
import uuid
from datetime import datetime, timezone
from typing import ClassVar
from unittest.mock import patch

from sqlalchemy import select

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.delivery.providers.base import (
    IncrementalSyncCapable,
    IncrementalSyncResult,
    ProviderSyncError,
    RawEmailMessage,
)
from app.models.company_profile import CompanyProfile
from app.models.email_message import EmailMessage
from app.models.enums import MailboxSyncStatus, ProviderConnectionStatus, UserRole
from app.models.mailbox_sync_state import MailboxSyncState
from app.models.provider_connection import ProviderConnection
from app.models.user import User
from app.reply_intelligence import sync_worker

_FAKE_CREDENTIAL = {"access_token": "fake-access-token", "refresh_token": "fake-refresh-token", "expires_at": None}


def _now():
    return datetime.now(timezone.utc)


def _raw_message(message_id: str, internet_message_id: str) -> RawEmailMessage:
    return RawEmailMessage(
        provider_message_id=message_id,
        provider_thread_id="thread-1",
        internet_message_id=internet_message_id,
        in_reply_to=None,
        references=None,
        from_email="buyer@example.com",
        from_name="Buyer",
        subject="Quote request",
        body_text=None,
        body_html="<p>hello</p>",
        sent_at=_now(),
        received_at=_now(),
        has_attachments=False,
        attachments=[],
    )


class _StubProvider(IncrementalSyncCapable):
    """A deterministic, in-memory stand-in for a real
    IncrementalSyncCapable provider - each test configures a fixed
    sequence of results (or exceptions) to return, one per call, so the
    exact tick-by-tick behavior under test is fully controlled."""

    key = "stub_test_provider"
    read_scopes: ClassVar[list[str]] = ["stub.read"]

    def __init__(self, pages: list):
        self._pages = list(pages)
        self.call_count = 0

    def fetch_messages_incremental(self, credential_payload, cursor, max_results):
        self.call_count += 1
        page = self._pages.pop(0)
        if isinstance(page, Exception):
            raise page
        return page


class TestSyncWorkerCursorContract(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        self.user = User(
            email=f"m6.2-cursor-test-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN
        )
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="Cursor Contract Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.flush()

        self.connection = ProviderConnection(
            company_profile_id=self.company_profile.id,
            provider_key="stub_test_provider",
            status=ProviderConnectionStatus.CONNECTED,
        )
        self.db.add(self.connection)
        self.db.commit()

    def tearDown(self):
        self.db.query(EmailMessage).filter(EmailMessage.provider_connection_id == self.connection.id).delete()
        self.db.query(MailboxSyncState).filter(MailboxSyncState.provider_connection_id == self.connection.id).delete()
        self.db.commit()
        self.db.query(ProviderConnection).filter(ProviderConnection.id == self.connection.id).delete()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    def _run_tick(self, stub: _StubProvider) -> int:
        with patch("app.reply_intelligence.sync_worker.get_provider", return_value=stub), patch(
            "app.reply_intelligence.sync_worker.refresh_credential_if_needed", return_value=_FAKE_CREDENTIAL
        ):
            return sync_worker.sync_one_connection(self.db, self.connection)

    def _sync_state(self) -> MailboxSyncState:
        return self.db.scalar(
            select(MailboxSyncState).where(MailboxSyncState.provider_connection_id == self.connection.id)
        )

    def _message_count(self) -> int:
        return self.db.query(EmailMessage).filter(EmailMessage.provider_connection_id == self.connection.id).count()

    # --- initial sync -----------------------------------------------------
    def test_initial_sync_persists_messages_and_advances_cursor(self):
        stub = _StubProvider(
            [
                IncrementalSyncResult(
                    messages=[_raw_message("m1", "<m1@example.com>"), _raw_message("m2", "<m2@example.com>")],
                    next_cursor="cursor-1",
                    has_more=False,
                )
            ]
        )
        inserted = self._run_tick(stub)
        self.assertEqual(inserted, 2)

        state = self._sync_state()
        self.assertIsNotNone(state, "MailboxSyncState should be auto-created on first tick for this connection")
        self.assertEqual(state.cursor, "cursor-1")
        self.assertEqual(state.last_sync_status, MailboxSyncStatus.OK)
        self.assertIsNotNone(state.sync_window_start, "sync_window_start should be set on the first-ever tick")

        messages = self.db.query(EmailMessage).filter(EmailMessage.provider_connection_id == self.connection.id).all()
        self.assertEqual(len(messages), 2)
        self.assertTrue(all(m.conversation_id is None for m in messages), "M6.2 must never assign conversation_id")

    # --- duplicate handling within one tick --------------------------------
    def test_duplicate_message_within_same_tick_is_skipped_not_fatal(self):
        stub = _StubProvider(
            [
                IncrementalSyncResult(
                    messages=[_raw_message("m1", "<dup@example.com>"), _raw_message("m1-again", "<dup@example.com>")],
                    next_cursor="cursor-1",
                )
            ]
        )
        inserted = self._run_tick(stub)
        self.assertEqual(inserted, 1, "the second message shares an internet_message_id and must be skipped, not counted")
        self.assertEqual(self._message_count(), 1)

    # --- rerun idempotency ---------------------------------------------------
    def test_rerun_with_same_messages_produces_no_duplicates(self):
        raw = _raw_message("m1", "<rerun@example.com>")
        stub = _StubProvider(
            [
                IncrementalSyncResult(messages=[raw], next_cursor="cursor-1"),
                IncrementalSyncResult(messages=[raw], next_cursor="cursor-2"),  # provider re-delivers the same message
            ]
        )
        first_inserted = self._run_tick(stub)
        second_inserted = self._run_tick(stub)

        self.assertEqual(first_inserted, 1)
        self.assertEqual(second_inserted, 0, "already-synced message must be skipped on rerun, not re-inserted")
        self.assertEqual(self._message_count(), 1)
        # the cursor still advances even on an all-duplicate tick - a quiet
        # or fully-duplicate page is still forward progress from the
        # provider's point of view.
        self.assertEqual(self._sync_state().cursor, "cursor-2")

    # --- crash/failure safety: a later failed tick must never undo an
    # earlier successful one, and must never advance the cursor past the
    # point it actually reached -------------------------------------------
    def test_failed_tick_does_not_lose_previously_synced_messages_or_corrupt_cursor(self):
        stub = _StubProvider(
            [
                IncrementalSyncResult(messages=[_raw_message("m1", "<safe@example.com>")], next_cursor="cursor-1"),
                ProviderSyncError("simulated transient Graph failure"),
            ]
        )
        first_inserted = self._run_tick(stub)
        self.assertEqual(first_inserted, 1)

        second_inserted = self._run_tick(stub)
        self.assertEqual(second_inserted, 0, "a failed tick inserts nothing")

        # tick 1's message must still be present - tick 2 failing must not
        # roll back already-committed prior work.
        self.assertEqual(self._message_count(), 1)

        state = self._sync_state()
        # the cursor must remain at tick 1's value - tick 2 never reached
        # the point in sync_one_connection where the cursor is advanced.
        self.assertEqual(state.cursor, "cursor-1")
        self.assertEqual(state.last_sync_status, MailboxSyncStatus.ERROR)
        self.assertEqual(state.attempt_count, 1)

    # --- a subsequent successful tick recovers cleanly after a failure ----
    def test_tick_after_a_failure_recovers_and_resumes_from_last_good_cursor(self):
        stub = _StubProvider(
            [
                IncrementalSyncResult(messages=[_raw_message("m1", "<first@example.com>")], next_cursor="cursor-1"),
                ProviderSyncError("simulated transient Graph failure"),
                IncrementalSyncResult(messages=[_raw_message("m2", "<second@example.com>")], next_cursor="cursor-2"),
            ]
        )
        self._run_tick(stub)  # tick 1: OK, cursor-1
        self._run_tick(stub)  # tick 2: fails, cursor stays at cursor-1
        third_inserted = self._run_tick(stub)  # tick 3: OK again

        self.assertEqual(third_inserted, 1)
        self.assertEqual(self._message_count(), 2)
        state = self._sync_state()
        self.assertEqual(state.cursor, "cursor-2")
        self.assertEqual(state.last_sync_status, MailboxSyncStatus.OK)
        self.assertEqual(state.attempt_count, 0, "a successful tick must reset attempt_count back to 0")


if __name__ == "__main__":
    unittest.main()
