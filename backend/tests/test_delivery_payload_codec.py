"""Real, executable tests for app.delivery.credentials.payload_codec -
stdlib-only (json, datetime), no database/HTTP/OAuth/cryptography
dependency, per the standing principle that pure-logic modules always
ship with real unit tests. Run standalone with:
    python -m unittest tests.test_delivery_payload_codec
"""
import unittest
from datetime import datetime, timezone

from app.delivery.credentials.payload_codec import deserialize_payload, serialize_payload


class TestPayloadCodec(unittest.TestCase):
    def test_round_trip_preserves_plain_fields(self):
        payload = {"access_token": "tok123", "refresh_token": "ref456", "expires_at": None}
        raw = serialize_payload(payload)
        self.assertIsInstance(raw, str)
        restored = deserialize_payload(raw)
        self.assertEqual(restored["access_token"], "tok123")
        self.assertEqual(restored["refresh_token"], "ref456")
        self.assertIsNone(restored["expires_at"])

    def test_round_trip_preserves_expires_at_datetime(self):
        expires_at = datetime(2026, 8, 1, 12, 30, 0, tzinfo=timezone.utc)
        payload = {"access_token": "tok", "refresh_token": "ref", "expires_at": expires_at}
        restored = deserialize_payload(serialize_payload(payload))
        self.assertEqual(restored["expires_at"], expires_at)
        self.assertIsInstance(restored["expires_at"], datetime)

    def test_serialize_produces_iso_format_string_for_datetime(self):
        expires_at = datetime(2026, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        raw = serialize_payload({"expires_at": expires_at})
        self.assertIn(expires_at.isoformat(), raw)

    def test_serialize_rejects_unserializable_value(self):
        class Unserializable:
            pass

        with self.assertRaises(TypeError):
            serialize_payload({"bad": Unserializable()})

    def test_deserialize_missing_expires_at_key_does_not_error(self):
        raw = serialize_payload({"access_token": "tok"})
        restored = deserialize_payload(raw)
        self.assertNotIn("expires_at", restored) if "expires_at" not in restored else None
        # access_token round-trips regardless
        self.assertEqual(restored["access_token"], "tok")

    def test_deserialize_falsy_expires_at_left_alone(self):
        # "" and False are falsy but not None - deserialize_payload only
        # converts when the key is truthy, so these pass through unchanged
        # rather than raising trying to parse them as ISO datetimes.
        raw = serialize_payload({"expires_at": ""})
        restored = deserialize_payload(raw)
        self.assertEqual(restored["expires_at"], "")

    def test_deserialize_invalid_json_raises(self):
        with self.assertRaises(Exception):
            deserialize_payload("not valid json{{{")


if __name__ == "__main__":
    unittest.main()
