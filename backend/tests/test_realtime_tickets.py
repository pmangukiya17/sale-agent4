"""
Unit tests for app/realtime/tickets.py - no database required (this
module never touches `events`, `notifications`, or any other table; see
its own docstring for why it's a stateless JWT, not a persisted row).
Covers: a genuine round trip, rejection of an expired ticket, rejection
of a normal access token (missing the `purpose` claim), and rejection of
a tampered/garbage token.

Run standalone with:
    python -m unittest tests.test_realtime_tickets
"""
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings
from app.core.security import create_access_token
from app.realtime.tickets import create_stream_ticket, verify_stream_ticket


class TestRealtimeTickets(unittest.TestCase):
    def test_round_trip(self):
        user_id = uuid.uuid4()
        company_profile_id = uuid.uuid4()

        ticket = create_stream_ticket(user_id=user_id, company_profile_id=company_profile_id)
        decoded = verify_stream_ticket(ticket)

        self.assertIsNotNone(decoded)
        decoded_user_id, decoded_company_profile_id = decoded
        self.assertEqual(decoded_user_id, user_id)
        self.assertEqual(decoded_company_profile_id, company_profile_id)

    def test_expired_ticket_is_rejected(self):
        user_id = uuid.uuid4()
        company_profile_id = uuid.uuid4()
        # Hand-crafted, already-expired token - same shape
        # create_stream_ticket produces, but with `exp` in the past.
        expired = jwt.encode(
            {
                "sub": str(user_id),
                "company_profile_id": str(company_profile_id),
                "purpose": "realtime_stream",
                "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        self.assertIsNone(verify_stream_ticket(expired))

    def test_normal_access_token_is_rejected(self):
        """A normal, valid, unexpired access token (create_access_token)
        must NOT be usable as a stream ticket - it has no `purpose`
        claim, which is the whole point of the distinction (see
        tickets.py's own docstring)."""
        access_token = create_access_token(subject=str(uuid.uuid4()))
        self.assertIsNone(verify_stream_ticket(access_token))

    def test_garbage_token_is_rejected(self):
        self.assertIsNone(verify_stream_ticket("not-a-real-token"))

    def test_ticket_with_wrong_purpose_claim_is_rejected(self):
        user_id = uuid.uuid4()
        company_profile_id = uuid.uuid4()
        wrong_purpose = jwt.encode(
            {
                "sub": str(user_id),
                "company_profile_id": str(company_profile_id),
                "purpose": "something_else",
                "exp": datetime.now(timezone.utc) + timedelta(seconds=60),
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        self.assertIsNone(verify_stream_ticket(wrong_purpose))


if __name__ == "__main__":
    unittest.main()
