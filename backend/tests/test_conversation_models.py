"""
Real, executable tests for the M6.1 persistent conversation model
(Conversation/EmailMessage/ConversationParticipant). Unlike M5 Layer 3's
tests (oauth_state, payload_codec, scheduler_windows, timezone_resolver),
these are NOT pure-logic - M6.1 is schema only, no business logic yet, so
what actually needs proving is that the real Postgres constraints
declared in migration 0009 behave as designed: the nullable-prospect
design genuinely persists (not just compiles), the partial unique dedup
index genuinely raises on a real duplicate, cascade deletes genuinely
cascade. Requires a real database connection (SessionLocal, the same one
the app itself uses) - run inside the backend container against the real
Postgres, same as smoke_test.py; not runnable in a sandbox with no
Docker/Postgres access.

Every fixture row this module creates is explicitly deleted in tearDown,
children before parents - no transaction/savepoint trick, matching this
project's existing ad hoc test-cleanup style (nothing elsewhere in this
codebase uses pytest fixtures or a rollback-based test-isolation pattern,
so this doesn't introduce one either).

Run standalone with:
    python -m unittest tests.test_conversation_models
"""
import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

# Must be imported before any ORM operation that triggers configure_mappers()
# (the first query/flush/commit in this process). CompanyProfile declares
# `relationship("Industry")` (see company_profile.py) as a lazy string -
# company_profile.py itself only imports the company_profile_industries
# association TABLE, never the Industry model CLASS, so nothing in this
# test module's own direct imports (CompanyProfile/Conversation/
# EmailMessage/ConversationParticipant/Prospect/ProspectContact/
# ProviderConnection/User) ever causes Industry to be registered.
# app.db.base imports every model in the codebase for exactly this reason
# - the identical fix already applied to app/delivery/worker.py after the
# same failure mode surfaced there during M5 Layer 7 verification (see
# that module's own docstring). Import order relative to the other
# imports below doesn't matter - only that this happens before the first
# real ORM operation, which setUp() below is.
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


def _now():
    return datetime.now(timezone.utc)


class TestConversationModels(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        self.user = User(
            email=f"m6.1-test-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN
        )
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M6.1 Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.flush()

        self.prospect = Prospect(
            company_profile_id=self.company_profile.id,
            name="M6.1 Test Prospect",
            first_discovered_at=_now(),
            last_seen_at=_now(),
        )
        self.db.add(self.prospect)
        self.db.flush()

        self.prospect_contact = ProspectContact(
            prospect_id=self.prospect.id, name="Test Contact", email="contact@example.com"
        )
        self.db.add(self.prospect_contact)
        self.db.flush()

        self.connection = ProviderConnection(
            company_profile_id=self.company_profile.id,
            provider_key="outlook",
            status=ProviderConnectionStatus.CONNECTED,
        )
        self.db.add(self.connection)
        self.db.commit()

        self._conversation_ids: list[uuid.UUID] = []

    def tearDown(self):
        # Children before parents. Deleting a Conversation cascades to its
        # own EmailMessage/ConversationParticipant rows at the DB level
        # (ondelete=CASCADE), so nothing else needs deleting per-message.
        for conversation_id in self._conversation_ids:
            self.db.query(Conversation).filter(Conversation.id == conversation_id).delete()
        self.db.commit()
        self.db.query(ProviderConnection).filter(ProviderConnection.id == self.connection.id).delete()
        self.db.query(ProspectContact).filter(ProspectContact.id == self.prospect_contact.id).delete()
        self.db.query(Prospect).filter(Prospect.id == self.prospect.id).delete()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    def _make_conversation(self, **overrides) -> Conversation:
        kwargs = dict(
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            prospect_id=self.prospect.id,
            prospect_contact_id=self.prospect_contact.id,
        )
        kwargs.update(overrides)
        conversation = Conversation(**kwargs)
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        self._conversation_ids.append(conversation.id)
        return conversation

    # --- the nullable prospect/prospect_contact design (the M6.1 plan's
    # own correction over the master M6 plan's original NOT NULL) actually
    # persists, not just declares -------------------------------------------
    def test_conversation_with_no_resolved_prospect_persists(self):
        conversation = self._make_conversation(prospect_id=None, prospect_contact_id=None)
        self.db.refresh(conversation)
        self.assertIsNone(conversation.prospect_id)
        self.assertIsNone(conversation.prospect_contact_id)
        self.assertEqual(conversation.company_profile_id, self.company_profile.id)

    def test_conversation_defaults_to_open_status(self):
        conversation = self._make_conversation()
        self.assertEqual(conversation.status, ConversationStatus.OPEN)

    # --- the partial unique dedup index is real, not just documented
    # intent -------------------------------------------------------------
    def test_duplicate_internet_message_id_same_connection_rejected(self):
        conversation = self._make_conversation()
        first = EmailMessage(
            conversation_id=conversation.id,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            provider="outlook",
            internet_message_id="<dup@example.com>",
            direction=MessageDirection.INBOUND,
        )
        self.db.add(first)
        self.db.commit()

        duplicate = EmailMessage(
            conversation_id=conversation.id,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            provider="outlook",
            internet_message_id="<dup@example.com>",
            direction=MessageDirection.INBOUND,
        )
        self.db.add(duplicate)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_null_internet_message_id_does_not_collide(self):
        # The partial index only applies WHERE internet_message_id IS NOT
        # NULL - two messages missing the header entirely must NOT be
        # treated as duplicates of each other (a real, if rare, case: not
        # every malformed email has a Message-ID).
        conversation = self._make_conversation()
        for _ in range(2):
            message = EmailMessage(
                conversation_id=conversation.id,
                company_profile_id=self.company_profile.id,
                provider_connection_id=self.connection.id,
                provider="outlook",
                internet_message_id=None,
                direction=MessageDirection.INBOUND,
            )
            self.db.add(message)
        self.db.commit()  # must not raise

    # --- cascade delete: conversation -> messages/participants -------------
    def test_deleting_conversation_cascades_to_messages_and_participants(self):
        conversation = self._make_conversation()
        message = EmailMessage(
            conversation_id=conversation.id,
            company_profile_id=self.company_profile.id,
            provider_connection_id=self.connection.id,
            provider="outlook",
            internet_message_id=f"<{uuid.uuid4()}@example.com>",
            direction=MessageDirection.INBOUND,
        )
        participant = ConversationParticipant(
            conversation_id=conversation.id, email="stakeholder@example.com", role=ConversationParticipantRole.CC
        )
        self.db.add_all([message, participant])
        self.db.commit()
        message_id, participant_id = message.id, participant.id

        self.db.query(Conversation).filter(Conversation.id == conversation.id).delete()
        self.db.commit()
        self._conversation_ids.remove(conversation.id)  # already gone; tearDown shouldn't touch it again

        self.assertIsNone(self.db.get(EmailMessage, message_id))
        self.assertIsNone(self.db.get(ConversationParticipant, participant_id))

    # --- one row per (conversation, email) ----------------------------------
    def test_duplicate_participant_email_same_conversation_rejected(self):
        conversation = self._make_conversation()
        self.db.add(
            ConversationParticipant(
                conversation_id=conversation.id, email="dup@example.com", role=ConversationParticipantRole.TO
            )
        )
        self.db.commit()
        self.db.add(
            ConversationParticipant(
                conversation_id=conversation.id, email="dup@example.com", role=ConversationParticipantRole.CC
            )
        )
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    # --- unresolved participant persists without inventing a
    # ProspectContact - "AI/system recommends, human decides" boundary
    # applies even at the schema level: nothing here auto-creates one -----
    def test_unresolved_participant_persists_without_prospect_contact(self):
        conversation = self._make_conversation()
        participant = ConversationParticipant(
            conversation_id=conversation.id, email="unknown@example.com", role=ConversationParticipantRole.FROM_
        )
        self.db.add(participant)
        self.db.commit()
        self.db.refresh(participant)
        self.assertIsNone(participant.prospect_contact_id)


if __name__ == "__main__":
    unittest.main()
