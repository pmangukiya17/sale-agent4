"""
Real, DB-backed tests of the M6.3 threading algorithm
(app/reply_intelligence/thread_matching.py) and the worker that drives it
(app/reply_intelligence/thread_builder.py) - covering every scenario from
the approved M6.3 verification plan: new conversation creation, existing
conversation matching (provider thread id / In-Reply-To / References),
reply correlation to an outbound send, duplicate handling, out-of-order
arrival, missing headers, multi-participant conversations,
provider-independent behavior, the Message-ID-wins conflict rule, and the
strengthened subject-fallback conditions (normalized subject match +
participant overlap + Conversation.status == OPEN, all three required).

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_thread_builder
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
from app.models.conversation_participant import ConversationParticipant
from app.models.email_message import EmailMessage
from app.models.enums import (
    ConversationParticipantRole,
    ConversationStatus,
    MessageDirection,
    ProviderConnectionStatus,
    UserRole,
)
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.provider_connection import ProviderConnection
from app.models.user import User
from app.reply_intelligence import thread_builder
from app.reply_intelligence.thread_matching import UNTHREADED_RETRY_WINDOW_MINUTES


def _now():
    return datetime.now(timezone.utc)


class TestThreadBuilder(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        self.user = User(email=f"m6.3-test-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M6.3 Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.flush()

        self.prospect = Prospect(
            company_profile_id=self.company_profile.id, name="M6.3 Prospect", first_discovered_at=_now(), last_seen_at=_now()
        )
        self.db.add(self.prospect)
        self.db.flush()

        self.known_contact = ProspectContact(prospect_id=self.prospect.id, name="Known Buyer", email="buyer@example.com")
        self.db.add(self.known_contact)
        self.db.flush()

        self.connection = ProviderConnection(
            company_profile_id=self.company_profile.id, provider_key="outlook", status=ProviderConnectionStatus.CONNECTED
        )
        self.db.add(self.connection)
        self.db.commit()

        # Kept for backward compatibility with test methods below that
        # still append to these - harmless no-ops now that tearDown (see
        # below) no longer reads either list. The bug that made this
        # necessary: several test methods below append a newly-created
        # Conversation's id to _conversation_ids AFTER one or more
        # assertions, not before. process_one_message()/run_one_tick()
        # commit their work internally regardless of what a test asserts
        # afterward - so a test whose row-producing call succeeded but a
        # LATER assertion in the same method failed would raise before
        # ever reaching its own append() call, leaving that Conversation
        # committed in the database but absent from this list. tearDown
        # would then only delete the conversations it happened to know
        # about, never reach the leaked one, and the subsequent
        # ProviderConnection delete would fail with exactly the FK
        # violation this fix addresses (Conversation.provider_connection_id
        # is RESTRICT, migration 0009) - not an M6.3 logic bug, a test-
        # cleanup ordering bug.
        self._conversation_ids: list[uuid.UUID] = []
        self._email_message_ids: list[uuid.UUID] = []

    def tearDown(self):
        # Query-based cleanup, not ID-list-based - robust regardless of
        # whether every row this test created was successfully appended
        # to a tracking list before an assertion could have raised (see
        # the comment in setUp above for the exact failure mode this
        # replaces). Every row any test in this module can create is
        # reachable from self.company_profile.id / self.connection.id,
        # so scoping deletes by those instead of a manually-maintained
        # list can't miss anything a mid-test failure would otherwise
        # orphan.
        #
        # Dependency order: ConversationParticipant/EmailMessage both
        # cascade-delete automatically at the DB level when their parent
        # Conversation is deleted (ondelete=CASCADE, migration 0009), so
        # deleting every Conversation for this company handles those two
        # tables with no separate delete needed. What that does NOT catch
        # is an EmailMessage that was created but never successfully
        # threaded (conversation_id still NULL - e.g. a "waiting" case a
        # failed assertion left unresolved) - those never belonged to a
        # Conversation, so they're deleted directly by
        # provider_connection_id instead. ProviderConnection is deleted
        # last, once both of the above are guaranteed empty for it.
        self.db.rollback()  # discard any uncommitted state from a failed assertion mid-test

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
        self.db.query(ProspectContact).filter(ProspectContact.id == self.known_contact.id).delete()
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
        self._conversation_ids.append(conversation.id)
        return conversation

    def _make_email_message(self, **overrides) -> EmailMessage:
        kwargs = dict(
            conversation_id=None,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            provider="outlook",
            direction=MessageDirection.INBOUND,
            internet_message_id=f"<{uuid.uuid4()}@example.com>",
            from_email="stranger@example.com",
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
        self._email_message_ids.append(message.id)
        return message

    def _participant_emails(self, conversation_id: uuid.UUID) -> set[str]:
        return {
            p.email
            for p in self.db.query(ConversationParticipant).filter(ConversationParticipant.conversation_id == conversation_id).all()
        }

    # --- 1. new conversation creation ---------------------------------------
    def test_new_conversation_created_when_no_signal_matches(self):
        message = self._make_email_message(from_email="cold-lead@example.com", subject=f"Unique subject {uuid.uuid4()}")
        outcome = thread_builder.process_one_message(self.db, message)

        self.assertEqual(outcome, "created")
        self.db.refresh(message)
        self.assertIsNotNone(message.conversation_id)
        self._conversation_ids.append(message.conversation_id)

        conversation = self.db.get(Conversation, message.conversation_id)
        self.assertEqual(conversation.status, ConversationStatus.OPEN)
        self.assertIn("cold-lead@example.com", self._participant_emails(conversation.id))

    def test_new_conversation_resolves_prospect_contact_when_sender_is_known(self):
        message = self._make_email_message(from_email=self.known_contact.email, subject=f"Unique subject {uuid.uuid4()}")
        thread_builder.process_one_message(self.db, message)
        self.db.refresh(message)
        self._conversation_ids.append(message.conversation_id)

        conversation = self.db.get(Conversation, message.conversation_id)
        self.assertEqual(conversation.prospect_contact_id, self.known_contact.id)
        self.assertEqual(conversation.prospect_id, self.prospect.id)

    # --- 2. existing conversation matching: provider thread id -------------
    def test_matches_existing_conversation_via_provider_thread_id(self):
        conversation = self._make_conversation()
        self._make_email_message(conversation_id=conversation.id, provider_thread_id="graph-thread-1")

        new_message = self._make_email_message(provider_thread_id="graph-thread-1", subject=f"Different subject {uuid.uuid4()}")
        outcome = thread_builder.process_one_message(self.db, new_message)

        self.assertEqual(outcome, "matched")
        self.db.refresh(new_message)
        self.assertEqual(new_message.conversation_id, conversation.id)

    # --- existing conversation matching: In-Reply-To -----------------------
    def test_matches_existing_conversation_via_in_reply_to(self):
        conversation = self._make_conversation()
        parent = self._make_email_message(conversation_id=conversation.id, internet_message_id="<parent-1@example.com>")

        reply = self._make_email_message(in_reply_to="<parent-1@example.com>", subject=f"Re: {parent.subject}")
        outcome = thread_builder.process_one_message(self.db, reply)

        self.assertEqual(outcome, "matched")
        self.db.refresh(reply)
        self.assertEqual(reply.conversation_id, conversation.id)

    # --- existing conversation matching: References fallback --------------
    def test_matches_existing_conversation_via_references_when_direct_parent_missing(self):
        conversation = self._make_conversation()
        self._make_email_message(conversation_id=conversation.id, internet_message_id="<grandparent@example.com>")

        reply = self._make_email_message(
            in_reply_to="<parent-not-synced-yet@example.com>",
            references="<grandparent@example.com> <parent-not-synced-yet@example.com>",
        )
        outcome = thread_builder.process_one_message(self.db, reply)

        self.assertEqual(outcome, "matched")
        self.db.refresh(reply)
        self.assertEqual(reply.conversation_id, conversation.id)

    # --- 3. reply correlation to an outbound M5 send ------------------------
    def test_reply_correlates_to_a_prior_outbound_send(self):
        conversation = self._make_conversation(prospect_id=self.prospect.id, prospect_contact_id=self.known_contact.id)
        self._make_email_message(
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND,
            internet_message_id="<outbound-1@sales-agent.local>",
            from_email="sales@ourcompany.com",
        )

        reply = self._make_email_message(
            in_reply_to="<outbound-1@sales-agent.local>", from_email=self.known_contact.email, subject="Re: Quote request"
        )
        outcome = thread_builder.process_one_message(self.db, reply)

        self.assertEqual(outcome, "matched")
        self.db.refresh(reply)
        self.assertEqual(reply.conversation_id, conversation.id)

    # --- 4. duplicate handling: already-threaded rows are never reprocessed
    def test_run_one_tick_never_touches_already_threaded_messages(self):
        # Asserted against THIS test's own rows specifically, not a
        # global count from run_one_tick()'s return value -
        # run_one_tick() intentionally scans the whole email_messages
        # table (matching the real worker's actual, non-company-scoped
        # behavior), so a global "== 1" assertion would be fragile/wrong
        # if any other NULL-conversation_id row exists elsewhere in the
        # database at test time (a different company's data, or another
        # test's row, in a shared dev database) - this test only needs to
        # prove ITS OWN two rows behaved correctly, which a global count
        # can't guarantee either way.
        conversation = self._make_conversation()
        already_threaded = self._make_email_message(conversation_id=conversation.id)

        pending = self._make_email_message(from_email="new-lead@example.com", subject=f"Unique {uuid.uuid4()}")

        thread_builder.run_one_tick()

        # run_one_tick() updates both rows through its OWN, separate
        # SessionLocal() instances (fresh session per message - see
        # thread_builder.py's own docstring), not through self.db. Both
        # `pending` and `already_threaded` are already present in
        # self.db's identity map (created via self.db earlier in this
        # test) - self.db.get() returns an identity-mapped object as-is
        # without re-querying, so it can read back a stale, pre-update
        # snapshot even though the row was correctly updated in the
        # database by the other session. Diagnosed via instrumentation:
        # the batch included pending.id, run_one_tick() reported
        # {"created": 1}, and a raw SQL SELECT confirmed conversation_id
        # was written correctly - self.db.get() alone returned the stale
        # object; self.db.refresh() immediately showed the correct value.
        # This is a test-only session-staleness issue, not a production
        # bug - explicit refresh() below, not a code change.
        self.db.refresh(pending)
        self.assertIsNotNone(pending.conversation_id, "the NULL-conversation_id message should have been threaded")

        self.db.refresh(already_threaded)
        self.assertEqual(already_threaded.conversation_id, conversation.id, "an already-threaded row must never be reassigned")

    # --- 5. out-of-order arrival: reply synced before its parent -----------
    def test_reply_synced_before_parent_waits_then_resolves_once_parent_arrives(self):
        reply = self._make_email_message(
            in_reply_to="<not-yet-synced-parent@example.com>",
            references="<not-yet-synced-parent@example.com>",
            synced_at=_now(),  # "young" - still within the retry window
        )
        first_outcome = thread_builder.process_one_message(self.db, reply)
        self.assertEqual(first_outcome, "waiting")
        self.db.refresh(reply)
        self.assertIsNone(reply.conversation_id)

        # the parent "arrives" (a later sync tick synced it) and gets
        # threaded first, on its own.
        conversation = self._make_conversation()
        self._make_email_message(conversation_id=conversation.id, internet_message_id="<not-yet-synced-parent@example.com>")

        second_outcome = thread_builder.process_one_message(self.db, reply)
        self.assertEqual(second_outcome, "matched")
        self.db.refresh(reply)
        self.assertEqual(reply.conversation_id, conversation.id)

    def test_waiting_expires_after_the_retry_window_and_falls_through(self):
        stale_cutoff = _now() - timedelta(minutes=UNTHREADED_RETRY_WINDOW_MINUTES + 5)
        reply = self._make_email_message(
            in_reply_to="<a-parent-that-will-never-arrive@example.com>",
            synced_at=stale_cutoff,
            from_email="patient-lead@example.com",
            subject=f"Old unmatched thread {uuid.uuid4()}",
        )
        outcome = thread_builder.process_one_message(self.db, reply)

        self.assertEqual(outcome, "created", "past the retry window, an unresolved parent must not wait forever")
        self.db.refresh(reply)
        self.assertIsNotNone(reply.conversation_id)
        self._conversation_ids.append(reply.conversation_id)

    # --- 6. missing headers entirely ----------------------------------------
    def test_message_with_no_signals_at_all_still_gets_threaded(self):
        message = self._make_email_message(
            provider_thread_id=None, in_reply_to=None, references=None, subject=None, from_email="no-headers@example.com"
        )
        outcome = thread_builder.process_one_message(self.db, message)

        self.assertEqual(outcome, "created")
        self.db.refresh(message)
        self.assertIsNotNone(message.conversation_id)
        self._conversation_ids.append(message.conversation_id)

    # --- 7. multi-participant conversations ---------------------------------
    def test_to_and_cc_recipients_become_conversation_participants(self):
        message = self._make_email_message(
            from_email="buyer2@example.com",
            to_recipients=[{"email": "sales@ourcompany.com", "name": "Sales"}],
            cc_recipients=[{"email": "cc-stakeholder@example.com", "name": "CC Stakeholder"}],
            subject=f"Multi-participant {uuid.uuid4()}",
        )
        thread_builder.process_one_message(self.db, message)
        self.db.refresh(message)
        self._conversation_ids.append(message.conversation_id)

        participants = {
            p.email: p.role
            for p in self.db.query(ConversationParticipant).filter(ConversationParticipant.conversation_id == message.conversation_id).all()
        }
        self.assertEqual(participants.get("buyer2@example.com"), ConversationParticipantRole.FROM_)
        self.assertEqual(participants.get("sales@ourcompany.com"), ConversationParticipantRole.TO)
        self.assertEqual(participants.get("cc-stakeholder@example.com"), ConversationParticipantRole.CC)

    def test_returning_participant_role_updates_not_duplicates(self):
        message1 = self._make_email_message(from_email="repeat@example.com", subject=f"Thread A {uuid.uuid4()}")
        thread_builder.process_one_message(self.db, message1)
        self.db.refresh(message1)
        conversation_id = message1.conversation_id
        self._conversation_ids.append(conversation_id)

        # the same person now appears as a CC on a second message in the
        # SAME conversation (forced via provider_thread_id continuity).
        conv_first_message = self.db.get(EmailMessage, message1.id)
        conv_first_message.provider_thread_id = "continuity-thread"
        self.db.commit()

        message2 = self._make_email_message(
            provider_thread_id="continuity-thread", from_email="someone-else@example.com", cc_recipients=[{"email": "repeat@example.com"}]
        )
        thread_builder.process_one_message(self.db, message2)
        self.db.refresh(message2)
        self.assertEqual(message2.conversation_id, conversation_id)

        rows = self.db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conversation_id, ConversationParticipant.email == "repeat@example.com"
        ).all()
        self.assertEqual(len(rows), 1, "one row per (conversation, email) - a role change must update, not duplicate")
        self.assertEqual(rows[0].role, ConversationParticipantRole.CC)

    # --- 8. provider-independent behavior -----------------------------------
    def test_matching_behaves_identically_for_a_synthetic_second_provider(self):
        conversation = self._make_conversation()
        self._make_email_message(conversation_id=conversation.id, provider="fake_provider_2", provider_thread_id="fp2-thread-1")

        new_message = self._make_email_message(provider="fake_provider_2", provider_thread_id="fp2-thread-1", subject=f"Diff {uuid.uuid4()}")
        outcome = thread_builder.process_one_message(self.db, new_message)

        self.assertEqual(outcome, "matched")
        self.db.refresh(new_message)
        self.assertEqual(new_message.conversation_id, conversation.id, "thread_matching.py must never branch on EmailMessage.provider")

    # --- 9. conflict resolution: Message-ID wins over provider thread id ---
    def test_message_id_match_wins_over_conflicting_provider_thread_id(self):
        conversation_a = self._make_conversation()
        self._make_email_message(conversation_id=conversation_a.id, provider_thread_id="thread-a")

        conversation_b = self._make_conversation()
        self._make_email_message(conversation_id=conversation_b.id, internet_message_id="<b-parent@example.com>")

        # disagreeing signals: provider_thread_id points at A, In-Reply-To points at B.
        conflicted = self._make_email_message(provider_thread_id="thread-a", in_reply_to="<b-parent@example.com>")
        outcome = thread_builder.process_one_message(self.db, conflicted)

        self.assertEqual(outcome, "matched")
        self.db.refresh(conflicted)
        self.assertEqual(conflicted.conversation_id, conversation_b.id, "Message-ID identity must win over provider thread id on conflict")

    # --- 10. strengthened subject fallback: all three conditions required -
    def test_subject_fallback_never_attaches_to_a_closed_conversation(self):
        closed = self._make_conversation(status=ConversationStatus.CLOSED, conversation_key="quote request")
        self.db.add(ConversationParticipant(conversation_id=closed.id, email="overlap@example.com", role=ConversationParticipantRole.FROM_))
        self.db.commit()

        message = self._make_email_message(
            from_email="overlap@example.com", subject="Re: Quote Request", provider_thread_id=None, in_reply_to=None, references=None
        )
        outcome = thread_builder.process_one_message(self.db, message)

        self.assertEqual(outcome, "created", "subject fallback must never attach to a CLOSED conversation")
        self.db.refresh(message)
        self.assertNotEqual(message.conversation_id, closed.id)
        self._conversation_ids.append(message.conversation_id)

    def test_subject_fallback_requires_participant_overlap(self):
        open_conversation = self._make_conversation(status=ConversationStatus.OPEN, conversation_key="quote request")
        self.db.add(
            ConversationParticipant(conversation_id=open_conversation.id, email="someone@example.com", role=ConversationParticipantRole.FROM_)
        )
        self.db.commit()

        message = self._make_email_message(
            from_email="totally-unrelated@example.com", subject="Re: Quote Request", provider_thread_id=None, in_reply_to=None, references=None
        )
        outcome = thread_builder.process_one_message(self.db, message)

        self.assertEqual(outcome, "created", "matching subject alone, with no participant overlap, must not match")
        self.db.refresh(message)
        self.assertNotEqual(message.conversation_id, open_conversation.id)
        self._conversation_ids.append(message.conversation_id)

    def test_subject_fallback_matches_when_all_three_conditions_met(self):
        open_conversation = self._make_conversation(status=ConversationStatus.OPEN, conversation_key="quote request")
        self.db.add(
            ConversationParticipant(conversation_id=open_conversation.id, email="overlap2@example.com", role=ConversationParticipantRole.FROM_)
        )
        self.db.commit()

        message = self._make_email_message(
            from_email="overlap2@example.com", subject="Re: Quote Request", provider_thread_id=None, in_reply_to=None, references=None
        )
        outcome = thread_builder.process_one_message(self.db, message)

        self.assertEqual(outcome, "matched")
        self.db.refresh(message)
        self.assertEqual(message.conversation_id, open_conversation.id)


if __name__ == "__main__":
    unittest.main()
