"""
Real, executable tests for the M6.2 mailbox-sync schema
(MailboxSyncState/Attachment, plus email_messages.conversation_id's new
nullability) - same rationale as tests/test_conversation_models.py: this
phase is schema + a thin worker, so what needs proving is that the real
Postgres constraints declared in migration 0010 behave as designed, not
just that the Python compiles. Requires a real database connection
(SessionLocal) - run inside the backend container against the real
Postgres; not runnable in a sandbox with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_mailbox_sync_models
"""
import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.models.attachment import Attachment
from app.models.company_profile import CompanyProfile
from app.models.email_message import EmailMessage
from app.models.enums import MailboxSyncStatus, MessageDirection, ProviderConnectionStatus, UserRole
from app.models.mailbox_sync_state import MailboxSyncState
from app.models.provider_connection import ProviderConnection
from app.models.user import User


def _now():
    return datetime.now(timezone.utc)


class TestMailboxSyncModels(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        self.user = User(
            email=f"m6.2-test-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN
        )
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M6.2 Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.flush()

        self.connection = ProviderConnection(
            company_profile_id=self.company_profile.id,
            provider_key="outlook",
            status=ProviderConnectionStatus.CONNECTED,
        )
        self.db.add(self.connection)
        self.db.commit()

        self._email_message_ids: list[uuid.UUID] = []
        self._sync_state_ids: list[uuid.UUID] = []

    def tearDown(self):
        for email_message_id in self._email_message_ids:
            self.db.query(EmailMessage).filter(EmailMessage.id == email_message_id).delete()
        self.db.commit()
        for sync_state_id in self._sync_state_ids:
            self.db.query(MailboxSyncState).filter(MailboxSyncState.id == sync_state_id).delete()
        self.db.commit()
        self.db.query(ProviderConnection).filter(ProviderConnection.id == self.connection.id).delete()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    def _make_email_message(self, **overrides) -> EmailMessage:
        kwargs = dict(
            conversation_id=None,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            provider="outlook",
            internet_message_id=f"<{uuid.uuid4()}@example.com>",
            direction=MessageDirection.INBOUND,
        )
        kwargs.update(overrides)
        message = EmailMessage(**kwargs)
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        self._email_message_ids.append(message.id)
        return message

    # --- the M6.2 lifecycle correction over M6.1: conversation_id can be
    # NULL and genuinely persists that way, not just compiles -------------
    def test_email_message_with_null_conversation_id_persists(self):
        message = self._make_email_message()
        self.db.refresh(message)
        self.assertIsNone(message.conversation_id)

    # --- MailboxSyncState: one row per connection, enforced for real -----
    def test_mailbox_sync_state_created_with_defaults(self):
        state = MailboxSyncState(provider_connection_id=self.connection.id)
        self.db.add(state)
        self.db.commit()
        self.db.refresh(state)
        self._sync_state_ids.append(state.id)

        self.assertIsNone(state.cursor)
        self.assertIsNone(state.last_sync_status)
        self.assertEqual(state.attempt_count, 0)

    def test_duplicate_mailbox_sync_state_same_connection_rejected(self):
        first = MailboxSyncState(provider_connection_id=self.connection.id)
        self.db.add(first)
        self.db.commit()
        self._sync_state_ids.append(first.id)

        duplicate = MailboxSyncState(provider_connection_id=self.connection.id)
        self.db.add(duplicate)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_mailbox_sync_state_records_a_failed_tick(self):
        state = MailboxSyncState(
            provider_connection_id=self.connection.id,
            last_sync_status=MailboxSyncStatus.ERROR,
            last_sync_detail="Network error contacting Microsoft Graph",
            attempt_count=1,
        )
        self.db.add(state)
        self.db.commit()
        self.db.refresh(state)
        self._sync_state_ids.append(state.id)

        self.assertEqual(state.last_sync_status, MailboxSyncStatus.ERROR)
        self.assertEqual(state.attempt_count, 1)

    # --- Attachment: metadata-only child row, cascades with its parent ---
    def test_attachment_persists_and_links_to_email_message(self):
        message = self._make_email_message(has_attachments=True)
        attachment = Attachment(
            email_message_id=message.id,
            filename="quote.pdf",
            content_type="application/pdf",
            size_bytes=2048,
            provider_attachment_id="att-123",
        )
        self.db.add(attachment)
        self.db.commit()
        self.db.refresh(attachment)

        self.assertEqual(attachment.email_message_id, message.id)
        self.assertEqual(attachment.filename, "quote.pdf")

    def test_deleting_email_message_cascades_to_attachments(self):
        message = self._make_email_message(has_attachments=True)
        attachment = Attachment(email_message_id=message.id, filename="quote.pdf")
        self.db.add(attachment)
        self.db.commit()
        attachment_id = attachment.id

        self.db.query(EmailMessage).filter(EmailMessage.id == message.id).delete()
        self.db.commit()
        self._email_message_ids.remove(message.id)  # already gone; tearDown shouldn't touch it again

        self.assertIsNone(self.db.get(Attachment, attachment_id))

    # --- the M6.1 dedup index still works after migration 0010 made
    # conversation_id nullable - a real regression risk worth proving,
    # not just assuming an unrelated ALTER COLUMN left it alone ----------
    def test_duplicate_internet_message_id_still_rejected_with_null_conversation_id(self):
        internet_message_id = f"<{uuid.uuid4()}@example.com>"
        self._make_email_message(internet_message_id=internet_message_id)

        duplicate = EmailMessage(
            conversation_id=None,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            provider="outlook",
            internet_message_id=internet_message_id,
            direction=MessageDirection.INBOUND,
        )
        self.db.add(duplicate)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()


if __name__ == "__main__":
    unittest.main()
