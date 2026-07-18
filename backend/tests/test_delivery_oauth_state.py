"""Real, executable tests for app.delivery.oauth_state - stdlib-only
(json, base64, hmac, hashlib), no database/HTTP/OAuth-network dependency,
per the standing principle that pure-logic modules always ship with real
unit tests. Covers the Layer 5 signing correction (see the module's
docstring for why unsigned state wasn't sufficient even with an
authenticated completion endpoint). Run standalone with:
    python -m unittest tests.test_delivery_oauth_state
"""
import json
import unittest
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from unittest import mock

from app.delivery.oauth_state import OAuthStateError, decode_oauth_state, encode_oauth_state

_SECRET = "test-secret-do-not-use-in-production"
_OTHER_SECRET = "a-different-secret"


class TestOAuthState(unittest.TestCase):
    def test_round_trip_connect_flow_no_reconnect_id(self):
        company_id = uuid.uuid4()
        state = encode_oauth_state(company_profile_id=company_id, provider_key="gmail", secret=_SECRET)
        decoded = decode_oauth_state(state, secret=_SECRET)
        self.assertEqual(decoded["company_profile_id"], str(company_id))
        self.assertEqual(decoded["provider_key"], "gmail")
        self.assertIsNone(decoded["reconnect_connection_id"])
        self.assertIn("issued_at", decoded)

    def test_round_trip_reconnect_flow_carries_connection_id(self):
        company_id = uuid.uuid4()
        connection_id = uuid.uuid4()
        state = encode_oauth_state(
            company_profile_id=company_id, provider_key="outlook", secret=_SECRET, reconnect_connection_id=connection_id
        )
        decoded = decode_oauth_state(state, secret=_SECRET)
        self.assertEqual(decoded["reconnect_connection_id"], str(connection_id))
        self.assertEqual(decoded["provider_key"], "outlook")

    def test_state_is_opaque_base64_not_readable_plaintext(self):
        state = encode_oauth_state(company_profile_id=uuid.uuid4(), provider_key="gmail", secret=_SECRET)
        self.assertNotIn("{", state)
        self.assertNotIn('"', state)

    def test_decode_malformed_state_raises_oauth_state_error(self):
        with self.assertRaises(OAuthStateError):
            decode_oauth_state("not-valid-base64-or-json!!!", secret=_SECRET)

    def test_decode_empty_string_raises(self):
        with self.assertRaises(OAuthStateError):
            decode_oauth_state("", secret=_SECRET)

    def test_two_encodes_of_same_input_are_NOT_deterministic(self):
        # Was deterministic pre-signing (Layer 3); now issued_at makes
        # every encode unique even for identical logical input - this is
        # a deliberate behavior change flagged here so it's never mistaken
        # for a regression.
        company_id = uuid.uuid4()
        state_a = encode_oauth_state(company_profile_id=company_id, provider_key="gmail", secret=_SECRET)
        state_b = encode_oauth_state(company_profile_id=company_id, provider_key="gmail", secret=_SECRET)
        self.assertNotEqual(state_a, state_b)
        # but both still decode to the same logical fields
        decoded_a = decode_oauth_state(state_a, secret=_SECRET)
        decoded_b = decode_oauth_state(state_b, secret=_SECRET)
        self.assertEqual(decoded_a["company_profile_id"], decoded_b["company_profile_id"])

    # --- the actual security-relevant behavior ------------------------------

    def test_wrong_secret_is_rejected(self):
        state = encode_oauth_state(company_profile_id=uuid.uuid4(), provider_key="gmail", secret=_SECRET)
        with self.assertRaises(OAuthStateError):
            decode_oauth_state(state, secret=_OTHER_SECRET)

    def test_tampered_payload_is_rejected(self):
        """Simulates exactly the attack the module's docstring describes:
        take a validly-signed state, rewrite company_profile_id inside it
        without knowing the secret, and confirm decode rejects it rather
        than silently accepting the attacker's edited value."""
        state = encode_oauth_state(company_profile_id=uuid.uuid4(), provider_key="gmail", secret=_SECRET)
        envelope = json.loads(urlsafe_b64decode(state.encode("utf-8")).decode("utf-8"))
        envelope["payload"]["company_profile_id"] = str(uuid.uuid4())  # attacker rewrites the target business
        tampered = urlsafe_b64encode(json.dumps(envelope).encode("utf-8")).decode("utf-8")
        with self.assertRaises(OAuthStateError):
            decode_oauth_state(tampered, secret=_SECRET)

    def test_expired_state_is_rejected(self):
        with mock.patch("app.delivery.oauth_state.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2020, 1, 1, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat
            state = encode_oauth_state(company_profile_id=uuid.uuid4(), provider_key="gmail", secret=_SECRET)
        # Decoded for real, 20 minutes later - past the 10-minute default.
        with mock.patch("app.delivery.oauth_state.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=20)
            mock_dt.fromisoformat = datetime.fromisoformat
            with self.assertRaises(OAuthStateError):
                decode_oauth_state(state, secret=_SECRET)

    def test_state_within_max_age_is_accepted(self):
        state = encode_oauth_state(company_profile_id=uuid.uuid4(), provider_key="gmail", secret=_SECRET)
        # Decoded immediately - well within the default 600s window.
        decoded = decode_oauth_state(state, secret=_SECRET, max_age_seconds=600)
        self.assertIsNotNone(decoded)

    def test_custom_max_age_is_respected(self):
        state = encode_oauth_state(company_profile_id=uuid.uuid4(), provider_key="gmail", secret=_SECRET)
        with self.assertRaises(OAuthStateError):
            decode_oauth_state(state, secret=_SECRET, max_age_seconds=0)


if __name__ == "__main__":
    unittest.main()
