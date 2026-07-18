"""
Real, DB-backed tests of app/reply_intelligence/reply_intelligence_worker.py
- the M6.4 worker that reclassifies each Conversation's latest inbound
reply and writes reply_status/last_reply_at/last_reply_from/
needs_human_review. Covers: basic classification + field writes, ignoring
outbound-only conversations, ignoring never-threaded (conversation_id IS
NULL) messages, idempotent rerun, latest-reply-wins when a conversation
has multiple replies, the NEGATIVE/needs_human_review path end-to-end,
and going through the shared text-extraction helper against a
body_html-only message (the real Outlook shape).

Deliberately uses RulesReplyClassifier directly via the real registry
(REPLY_CLASSIFIER_BACKEND defaults to "rules") rather than a stub/mock -
the classifier itself is already covered in isolation by
test_rules_classifier.py; what these tests verify is the worker's own
orchestration (candidate selection, latest-message selection, field
writes, idempotency), which only makes sense wired to a real classifier.

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_reply_intelligence_worker
"""
import unittest
import uuid
from datetime import datetime, timedelta, timezone

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.models.company_profile import CompanyProfile
from app.models.conversation import Conversation
from app.models.email_message import EmailMessage
from app.models.enums import ConversationStatus, MessageDirection, ProviderConnectionStatus, ReplyStatus, UserRole
from app.models.prospect import Prospect
from app.models.provider_connection import ProviderConnection
from app.models.user import User
from app.reply_intelligence import reply_intelligence_worker


def _now():
    return datetime.now(timezone.utc)


class TestReplyIntelligenceWorker(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        self.user = User(email=f"m6.4-test-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M6.4 Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.flush()

        self.prospect = Prospect(
            company_profile_id=self.company_profile.id, name="M6.4 Prospect", first_discovered_at=_now(), last_seen_at=_now()
        )
        self.db.add(self.prospect)
        self.db.flush()

        self.connection = ProviderConnection(
            company_profile_id=self.company_profile.id, provider_key="outlook", status=ProviderConnectionStatus.CONNECTED
        )
        self.db.add(self.connection)
        self.db.commit()

    def tearDown(self):
        # Query-based cleanup, same discipline as test_thread_builder.py's
        # own tearDown - robust regardless of where a mid-test assertion
        # failure occurred.
        self.db.rollback()

        conversation_ids = [
            row.id
            for row in self.db.query(Conversation.id).filter(Conversation.company_profile_id == self.company_profile.id).all()
        ]
        if conversation_ids:
            self.db.query(Conversation).filter(Conversation.id.in_(conversation_ids)).delete(synchronize_session=False)
            self.db.commit()

        self.db.query(EmailMessage).filter(EmailMessage.provider_connection_id == self.connection.id).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(ProviderConnection).filter(ProviderConnection.id == self.connection.id).delete()
        self.db.query(Prospect).filter(Prospect.id == self.prospect.id).delete()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    # --- fixture helpers ----------------------------------------------------
    def _make_conversation(self, **overrides) -> Conversation:
        kwargs = dict(
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            status=ConversationStatus.OPEN,
            first_discovered_at=_now(),
        )
        kwargs.update(overrides)
        conversation = Conversation(**kwargs)
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def _make_email_message(self, **overrides) -> EmailMessage:
        kwargs = dict(
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            provider="outlook",
            direction=MessageDirection.INBOUND,
            internet_message_id=f"<{uuid.uuid4()}@example.com>",
            from_email="lead@example.com",
            subject="Quote request",
            sent_at=_now(),
            received_at=_now(),
            synced_at=_now(),
        )
        kwargs.update(overrides)
        message = EmailMessage(**kwargs)
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    # --- basic classification + field writes --------------------------------
    def test_classifies_latest_inbound_message_and_writes_conversation_fields(self):
        conversation = self._make_conversation()
        self._make_email_message(
            conversation_id=conversation.id,
            from_email="lead@example.com",
            body_text="Yes, interested - let's talk.",
        )

        counts = reply_intelligence_worker.run_one_tick()
        self.assertGreaterEqual(counts["classified"], 1)

        self.db.refresh(conversation)
        self.assertEqual(conversation.reply_status, ReplyStatus.POSITIVE)
        self.assertFalse(conversation.needs_human_review)
        self.assertEqual(conversation.last_reply_from, "lead@example.com")
        self.assertIsNotNone(conversation.last_reply_at)

    def test_negative_reply_sets_needs_human_review_true(self):
        conversation = self._make_conversation()
        self._make_email_message(conversation_id=conversation.id, body_text="Not interested, please remove me.")

        reply_intelligence_worker.run_one_tick()

        self.db.refresh(conversation)
        self.assertEqual(conversation.reply_status, ReplyStatus.NEGATIVE)
        self.assertTrue(conversation.needs_human_review)

    def test_reads_html_only_body_via_shared_text_extraction(self):
        # The real Outlook shape - body_text is never populated, only
        # body_html - proves the worker goes through
        # app.core.text_extraction.extract_plain_text rather than reading
        # body_text/body_html itself.
        conversation = self._make_conversation()
        self._make_email_message(conversation_id=conversation.id, body_text=None, body_html="<p>Not interested, thanks.</p>")

        reply_intelligence_worker.run_one_tick()

        self.db.refresh(conversation)
        self.assertEqual(conversation.reply_status, ReplyStatus.NEGATIVE)

    # --- ignores outbound / never-threaded ------------------------------------
    def test_conversation_with_only_outbound_messages_is_untouched(self):
        conversation = self._make_conversation()
        self._make_email_message(
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND,
            from_email="us@our-company.com",
            body_text="Following up on our quote.",
        )

        reply_intelligence_worker.run_one_tick()

        self.db.refresh(conversation)
        self.assertIsNone(conversation.reply_status)
        self.assertIsNone(conversation.last_reply_at)
        self.assertFalse(conversation.needs_human_review)

    def test_never_threaded_message_is_ignored_and_left_unmodified(self):
        # conversation_id IS NULL - Thread Builder's own queue, not Reply
        # Intelligence's. This message must be structurally invisible to
        # the worker's candidate query.
        orphan = self._make_email_message(conversation_id=None, body_text="Yes, interested.")

        reply_intelligence_worker.run_one_tick()

        self.db.refresh(orphan)
        self.assertIsNone(orphan.conversation_id, "Reply Intelligence must never assign conversation_id - that is Thread Builder's job")

    # --- idempotency / rerun safety --------------------------------------------
    def test_rerun_with_no_new_data_produces_identical_result(self):
        conversation = self._make_conversation()
        self._make_email_message(conversation_id=conversation.id, body_text="Let's schedule a call.")

        reply_intelligence_worker.run_one_tick()
        self.db.refresh(conversation)
        first_status = conversation.reply_status
        first_last_reply_at = conversation.last_reply_at
        first_last_reply_from = conversation.last_reply_from

        reply_intelligence_worker.run_one_tick()
        self.db.refresh(conversation)

        self.assertEqual(conversation.reply_status, first_status)
        self.assertEqual(conversation.last_reply_at, first_last_reply_at)
        self.assertEqual(conversation.last_reply_from, first_last_reply_from)

    # --- latest message wins ----------------------------------------------------
    def test_latest_inbound_message_wins_over_an_earlier_reply(self):
        conversation = self._make_conversation()
        earlier = _now() - timedelta(hours=2)
        later = _now()

        self._make_email_message(
            conversation_id=conversation.id,
            from_email="lead-old@example.com",
            body_text="Not interested.",
            received_at=earlier,
            sent_at=earlier,
        )
        self._make_email_message(
            conversation_id=conversation.id,
            from_email="lead-new@example.com",
            body_text="Actually, yes - let's talk.",
            received_at=later,
            sent_at=later,
        )

        reply_intelligence_worker.run_one_tick()

        self.db.refresh(conversation)
        self.assertEqual(conversation.reply_status, ReplyStatus.POSITIVE)
        self.assertEqual(conversation.last_reply_from, "lead-new@example.com")
        self.assertEqual(conversation.last_reply_at, later)

    def test_reclassifies_when_a_newer_reply_arrives_later(self):
        # Full-recompute design (no cursor against last_reply_at) - a
        # SECOND run_one_tick() after a new reply is added must pick up
        # the new reply, proving the worker isn't accidentally coupled to
        # any stale state from the first run.
        conversation = self._make_conversation()
        self._make_email_message(conversation_id=conversation.id, body_text="Not interested.", received_at=_now() - timedelta(hours=1))
        reply_intelligence_worker.run_one_tick()
        self.db.refresh(conversation)
        self.assertEqual(conversation.reply_status, ReplyStatus.NEGATIVE)

        self._make_email_message(conversation_id=conversation.id, body_text="Yes, let's talk.", received_at=_now())
        reply_intelligence_worker.run_one_tick()
        self.db.refresh(conversation)
        self.assertEqual(conversation.reply_status, ReplyStatus.POSITIVE)


if __name__ == "__main__":
    unittest.main()
