"""
Real, executable unit tests for app.delivery.timezone.resolver - pure,
stdlib-only logic (zoneinfo), so unlike most of Layer 3 these can actually
run without SQLAlchemy/FastAPI/network installed. Run with:

    python3 -m unittest tests.test_delivery_timezone_resolver -v

(from backend/, with backend/ on PYTHONPATH - see the verify_layer3.sh
script for the exact invocation used in CI/local verification.)
"""
import unittest
from datetime import date, datetime, time, timezone

from app.delivery.timezone.resolver import (
    is_valid_iana_timezone,
    local_window_to_utc,
    resolve_recipient_timezone,
)


class TestIsValidIanaTimezone(unittest.TestCase):
    def test_valid_zone(self):
        self.assertTrue(is_valid_iana_timezone("Europe/Berlin"))
        self.assertTrue(is_valid_iana_timezone("UTC"))
        self.assertTrue(is_valid_iana_timezone("Asia/Dubai"))

    def test_invalid_zone(self):
        self.assertFalse(is_valid_iana_timezone("Not/A_Real_Zone"))
        self.assertFalse(is_valid_iana_timezone(""))
        self.assertFalse(is_valid_iana_timezone(None))


class TestResolveRecipientTimezone(unittest.TestCase):
    def test_explicit_wins_when_valid(self):
        self.assertEqual(
            resolve_recipient_timezone("Europe/Berlin", "Asia/Dubai"), "Europe/Berlin"
        )

    def test_falls_back_to_country_default_when_explicit_missing(self):
        self.assertEqual(resolve_recipient_timezone(None, "Asia/Dubai"), "Asia/Dubai")

    def test_falls_back_to_country_default_when_explicit_invalid(self):
        # Defensive: a garbage value stored in a free-text column should
        # never propagate into the scheduler.
        self.assertEqual(resolve_recipient_timezone("not-a-zone", "Asia/Dubai"), "Asia/Dubai")

    def test_utc_fallback_when_nothing_valid(self):
        self.assertEqual(resolve_recipient_timezone(None, None), "UTC")
        self.assertEqual(resolve_recipient_timezone("garbage", "also-garbage"), "UTC")


class TestLocalWindowToUtc(unittest.TestCase):
    def test_berlin_summer_offset(self):
        # Europe/Berlin is UTC+2 in July (CEST, daylight saving).
        start_utc, end_utc = local_window_to_utc(
            date(2026, 7, 20), time(8, 0), time(18, 0), "Europe/Berlin"
        )
        self.assertEqual(start_utc, datetime(2026, 7, 20, 6, 0, tzinfo=timezone.utc))
        self.assertEqual(end_utc, datetime(2026, 7, 20, 16, 0, tzinfo=timezone.utc))

    def test_dubai_no_dst(self):
        # Asia/Dubai is a fixed UTC+4, no daylight saving.
        start_utc, end_utc = local_window_to_utc(
            date(2026, 1, 15), time(9, 0), time(17, 0), "Asia/Dubai"
        )
        self.assertEqual(start_utc, datetime(2026, 1, 15, 5, 0, tzinfo=timezone.utc))
        self.assertEqual(end_utc, datetime(2026, 1, 15, 13, 0, tzinfo=timezone.utc))

    def test_falls_back_to_utc_for_invalid_zone(self):
        start_utc, end_utc = local_window_to_utc(
            date(2026, 1, 15), time(9, 0), time(17, 0), "garbage-zone"
        )
        self.assertEqual(start_utc.hour, 9)
        self.assertEqual(end_utc.hour, 17)


if __name__ == "__main__":
    unittest.main()
