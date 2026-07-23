"""
Track C1 (dashboard-capabilities-architecture-plan.md): the Open
Conversations KPI's own endpoint,
GET /company-profiles/{id}/conversations/count. Real-DB test, same
conventions as test_conversation_models.py (direct route-function calls
against a real SessionLocal, explicit child-then-parent teardown, no
pytest fixtures/rollback-based isolation - this codebase doesn't use
either pattern anywhere else). Requires a real database connection - not
runnable in a sandbox with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_open_conversations_count
"""
import unittest
import uuid

# Must be imported before any ORM operation - see
# test_conversation_models.py's own docstring for the full explanation
# (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.api.routes.conversations import count_conversations
from app.models.company_profile import CompanyProfile
from app.models.conversation import Conversation
from app.models.enums import ConversationStatus, ProviderConnectionStatus, UserRole
from app.models.provider_connection import ProviderConnection
from app.models.user import User


class TestOpenConversationsCount(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        # Two entirely separate businesses/owners, so every assertion
        # below can prove tenant isolation, not just "the count works" -
        # same "prove isolation with two owners" pattern
        # test_track_b2_verification.py's legacy-gap tests already
        # established.
        self.user_a = User(email=f"c1-a-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.user_b = User(email=f"c1-b-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add_all([self.user_a, self.user_b])
        self.db.flush()

        self.profile_a = CompanyProfile(owner_user_id=self.user_a.id, name="C1 Test Co A")
        self.profile_b = CompanyProfile(owner_user_id=self.user_b.id, name="C1 Test Co B")
        self.db.add_all([self.profile_a, self.profile_b])
        self.db.flush()

        self.connection_a = ProviderConnection(
            company_profile_id=self.profile_a.id, provider_key="outlook", status=ProviderConnectionStatus.CONNECTED
        )
        self.connection_b = ProviderConnection(
            company_profile_id=self.profile_b.id, provider_key="outlook", status=ProviderConnectionStatus.CONNECTED
        )
        self.db.add_all([self.connection_a, self.connection_b])
        self.db.commit()

        # Business A: 2 open, 1 closed. Business B: 5 open - a
        # deliberately different, larger count than A's, so a test that
        # accidentally counted across both businesses would be caught
        # immediately by a wrong number, not masked by a coincidence.
        self.conversations_a = [
            Conversation(
                company_profile_id=self.profile_a.id,
                provider_connection_id=self.connection_a.id,
                status=ConversationStatus.OPEN,
            ),
            Conversation(
                company_profile_id=self.profile_a.id,
                provider_connection_id=self.connection_a.id,
                status=ConversationStatus.OPEN,
            ),
            Conversation(
                company_profile_id=self.profile_a.id,
                provider_connection_id=self.connection_a.id,
                status=ConversationStatus.CLOSED,
            ),
        ]
        self.conversations_b = [
            Conversation(
                company_profile_id=self.profile_b.id,
                provider_connection_id=self.connection_b.id,
                status=ConversationStatus.OPEN,
            )
            for _ in range(5)
        ]
        self.db.add_all(self.conversations_a + self.conversations_b)
        self.db.commit()

    def tearDown(self):
        for conv in self.conversations_a + self.conversations_b:
            self.db.query(Conversation).filter(Conversation.id == conv.id).delete()
        self.db.commit()
        self.db.query(ProviderConnection).filter(
            ProviderConnection.id.in_([self.connection_a.id, self.connection_b.id])
        ).delete(synchronize_session=False)
        self.db.query(CompanyProfile).filter(CompanyProfile.id.in_([self.profile_a.id, self.profile_b.id])).delete(
            synchronize_session=False
        )
        self.db.query(User).filter(User.id.in_([self.user_a.id, self.user_b.id])).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def test_counts_only_open_conversations_for_the_callers_own_business(self):
        result = count_conversations(status_filter=ConversationStatus.OPEN, profile=self.profile_a, db=self.db)
        self.assertEqual(result.count, 2)

    def test_counts_are_isolated_per_business(self):
        result = count_conversations(status_filter=ConversationStatus.OPEN, profile=self.profile_b, db=self.db)
        self.assertEqual(result.count, 5)

    def test_no_status_filter_counts_every_conversation_regardless_of_status(self):
        result = count_conversations(status_filter=None, profile=self.profile_a, db=self.db)
        self.assertEqual(result.count, 3)

    def test_zero_conversations_returns_zero_not_none(self):
        # A brand-new business with no conversations at all yet. Postgres
        # itself already returns 0 (not NULL) from a bare COUNT(*) over
        # zero rows, so this mostly guards the route's own `or 0` against
        # ever silently regressing to returning None over a real 200
        # response, rather than testing genuinely uncertain SQL behavior.
        user_c = User(email=f"c1-c-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(user_c)
        self.db.flush()
        profile_c = CompanyProfile(owner_user_id=user_c.id, name="C1 Test Co C - Empty")
        self.db.add(profile_c)
        self.db.commit()
        try:
            result = count_conversations(status_filter=ConversationStatus.OPEN, profile=profile_c, db=self.db)
            self.assertEqual(result.count, 0)
        finally:
            self.db.query(CompanyProfile).filter(CompanyProfile.id == profile_c.id).delete()
            self.db.query(User).filter(User.id == user_c.id).delete()
            self.db.commit()


if __name__ == "__main__":
    unittest.main()
