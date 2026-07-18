"""
Real, DB-backed tests of app/reply_intelligence/conversation_resolver.py -
the exact logic dispatch_service._record_outbound_conversation (M6.3)
depends on for outbound Conversation/ConversationParticipant handling.

Deliberately does NOT construct a full DeliveryQueueItem fixture chain
(DeliveryCampaign -> OutreachDraft -> OutreachRun -> ... back through
M1-M4) to test dispatch_service.dispatch() end-to-end - no test in this
codebase does that today (test_delivery_oauth_state.py/
payload_codec.py/scheduler_windows.py/timezone_resolver.py are all
pure-logic, no-DB tests), and building one from scratch here would be a
disproportionately large, fragile undertaking for what's actually being
verified. conversation_resolver.py's two functions are the real,
independently-testable unit dispatch_service calls; verifying them
directly, plus reading dispatch_service.py's own small, focused
integration point, gives real confidence without that cost. A live M5
send remains the actual end-to-end confirmation, same disclosed
real-provider boundary as every other send-path claim in this project.

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_conversation_resolver
"""
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.models.company_profile import CompanyProfile
from app.models.conversation import Conversation
from app.models.conversation_participant import ConversationParticipant
from app.models.enums import ConversationParticipantRole, ConversationStatus, ProviderConnectionStatus, UserRole
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.provider_connection import ProviderConnection
from app.models.user import User
from app.reply_intelligence.conversation_resolver import get_or_create_conversation_for_outbound, upsert_participant


def _now():
    return datetime.now(timezone.utc)


class TestConversationResolver(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        self.user = User(email=f"m6.3-resolver-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="Resolver Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.flush()

        self.prospect = Prospect(
            company_profile_id=self.company_profile.id, name="Resolver Prospect", first_discovered_at=_now(), last_seen_at=_now()
        )
        self.db.add(self.prospect)
        self.db.flush()

        self.contact = ProspectContact(prospect_id=self.prospect.id, name="Resolver Contact", email="contact@example.com")
        self.db.add(self.contact)
        self.db.flush()

        self.connection = ProviderConnection(
            company_profile_id=self.company_profile.id, provider_key="outlook", status=ProviderConnectionStatus.CONNECTED
        )
        self.db.add(self.connection)
        self.db.commit()

        self._conversation_ids: list[uuid.UUID] = []

    def tearDown(self):
        if self._conversation_ids:
            self.db.query(Conversation).filter(Conversation.id.in_(self._conversation_ids)).delete(synchronize_session=False)
            self.db.commit()
        self.db.query(ProviderConnection).filter(ProviderConnection.id == self.connection.id).delete()
        self.db.query(ProspectContact).filter(ProspectContact.id == self.contact.id).delete()
        self.db.query(Prospect).filter(Prospect.id == self.prospect.id).delete()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    # --- get_or_create_conversation_for_outbound -----------------------------
    def test_creates_a_new_conversation_when_none_exists(self):
        conversation = get_or_create_conversation_for_outbound(
            self.db,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            prospect_id=self.prospect.id,
            prospect_contact_id=self.contact.id,
            subject="Re: Quote request",
            sent_at=_now(),
        )
        self.db.commit()
        self._conversation_ids.append(conversation.id)

        self.assertEqual(conversation.status, ConversationStatus.OPEN)
        self.assertEqual(conversation.conversation_key, "quote request")

    def test_reuses_existing_open_conversation_for_same_contact(self):
        first = get_or_create_conversation_for_outbound(
            self.db,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            prospect_id=self.prospect.id,
            prospect_contact_id=self.contact.id,
            subject="Quote request",
            sent_at=_now(),
        )
        self.db.commit()
        self._conversation_ids.append(first.id)

        second = get_or_create_conversation_for_outbound(
            self.db,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            prospect_id=self.prospect.id,
            prospect_contact_id=self.contact.id,
            subject="Follow-up",
            sent_at=_now(),
        )
        self.db.commit()

        self.assertEqual(second.id, first.id, "a second outbound send to the same contact must reuse the OPEN conversation")

    def test_does_not_reuse_a_closed_conversation(self):
        closed = get_or_create_conversation_for_outbound(
            self.db,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            prospect_id=self.prospect.id,
            prospect_contact_id=self.contact.id,
            subject="Old thread",
            sent_at=_now(),
        )
        closed.status = ConversationStatus.CLOSED
        self.db.commit()
        self._conversation_ids.append(closed.id)

        new_one = get_or_create_conversation_for_outbound(
            self.db,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            prospect_id=self.prospect.id,
            prospect_contact_id=self.contact.id,
            subject="New thread",
            sent_at=_now(),
        )
        self.db.commit()
        self._conversation_ids.append(new_one.id)

        self.assertNotEqual(new_one.id, closed.id)
        self.assertEqual(new_one.status, ConversationStatus.OPEN)

    def test_last_message_at_only_advances_forward(self):
        earlier = _now()
        later = earlier + timedelta(hours=1)

        conversation = get_or_create_conversation_for_outbound(
            self.db,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            prospect_id=self.prospect.id,
            prospect_contact_id=self.contact.id,
            subject="Quote request",
            sent_at=later,
        )
        self.db.commit()
        self._conversation_ids.append(conversation.id)

        # a second call with an EARLIER sent_at (e.g. out-of-order
        # processing) must not rewind last_message_at.
        same_conversation = get_or_create_conversation_for_outbound(
            self.db,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            prospect_id=self.prospect.id,
            prospect_contact_id=self.contact.id,
            subject="Quote request",
            sent_at=earlier,
        )
        self.db.commit()

        self.assertEqual(same_conversation.id, conversation.id)
        self.assertEqual(same_conversation.last_message_at, later)

    # --- upsert_participant ---------------------------------------------------
    def test_upsert_creates_a_new_participant(self):
        conversation = get_or_create_conversation_for_outbound(
            self.db,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            prospect_id=self.prospect.id,
            prospect_contact_id=self.contact.id,
            subject="Quote request",
            sent_at=_now(),
        )
        self.db.commit()
        self._conversation_ids.append(conversation.id)

        participant = upsert_participant(
            self.db, conversation_id=conversation.id, email="new@example.com", name="New Person", role=ConversationParticipantRole.TO
        )
        self.db.commit()

        self.assertIsNotNone(participant)
        self.assertEqual(participant.role, ConversationParticipantRole.TO)

    def test_upsert_updates_role_on_existing_participant_without_duplicating(self):
        conversation = get_or_create_conversation_for_outbound(
            self.db,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            prospect_id=self.prospect.id,
            prospect_contact_id=self.contact.id,
            subject="Quote request",
            sent_at=_now(),
        )
        self.db.commit()
        self._conversation_ids.append(conversation.id)

        upsert_participant(self.db, conversation_id=conversation.id, email="dual@example.com", name=None, role=ConversationParticipantRole.CC)
        self.db.commit()
        upsert_participant(self.db, conversation_id=conversation.id, email="dual@example.com", name=None, role=ConversationParticipantRole.TO)
        self.db.commit()

        rows = self.db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conversation.id, ConversationParticipant.email == "dual@example.com"
        ).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].role, ConversationParticipantRole.TO)

    def test_upsert_with_no_email_is_a_safe_noop(self):
        conversation = get_or_create_conversation_for_outbound(
            self.db,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            prospect_id=self.prospect.id,
            prospect_contact_id=self.contact.id,
            subject="Quote request",
            sent_at=_now(),
        )
        self.db.commit()
        self._conversation_ids.append(conversation.id)

        result = upsert_participant(self.db, conversation_id=conversation.id, email=None, name=None, role=ConversationParticipantRole.CC)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
