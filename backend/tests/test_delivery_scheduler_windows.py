"""
Real, executable unit tests for app.delivery.scheduler.windows - pure,
stdlib-only logic. Run with:

    python3 -m unittest tests.test_delivery_scheduler_windows -v
"""
import random
import unittest
from datetime import datetime, timedelta, timezone

from app.delivery.scheduler.windows import generate_send_times


class TestGenerateSendTimes(unittest.TestCase):
    def setUp(self):
        self.window_start = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
        self.window_end = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)

    def test_zero_or_negative_count_returns_empty(self):
        self.assertEqual(
            generate_send_times(self.window_start, self.window_end, 0, 60, 300), []
        )
        self.assertEqual(
            generate_send_times(self.window_start, self.window_end, -5, 60, 300), []
        )

    def test_empty_or_inverted_window_returns_empty(self):
        self.assertEqual(
            generate_send_times(self.window_end, self.window_start, 5, 60, 300), []
        )
        self.assertEqual(
            generate_send_times(self.window_start, self.window_start, 5, 60, 300), []
        )

    def test_invalid_gap_bounds_raise(self):
        with self.assertRaises(ValueError):
            generate_send_times(self.window_start, self.window_end, 5, 300, 60)  # min > max
        with self.assertRaises(ValueError):
            generate_send_times(self.window_start, self.window_end, 5, -1, 60)

    def test_times_are_monotonically_increasing_and_within_window(self):
        rng = random.Random(42)
        times = generate_send_times(
            self.window_start, self.window_end, max_count=20,
            min_gap_seconds=60, max_gap_seconds=600, rng=rng,
        )
        self.assertEqual(len(times), 20)
        for t in times:
            self.assertGreaterEqual(t, self.window_start)
            self.assertLess(t, self.window_end)
        for a, b in zip(times, times[1:]):
            self.assertLess(a, b)

    def test_gaps_respect_min_and_max_when_no_hourly_limit(self):
        rng = random.Random(7)
        times = generate_send_times(
            self.window_start, self.window_end, max_count=15,
            min_gap_seconds=60, max_gap_seconds=300, rng=rng,
        )
        for a, b in zip(times, times[1:]):
            gap = (b - a).total_seconds()
            self.assertGreaterEqual(gap, 60)
            self.assertLessEqual(gap, 300)

    def test_matches_the_brief_example_shape_irregular_not_fixed_intervals(self):
        # The M5 brief's own example: 08:01, 08:05, 08:11, 08:17, 08:24,
        # 08:31 - irregular gaps, not a fixed cadence. Assert the generated
        # gaps are NOT all identical (a fixed-interval bug would produce
        # constant gaps).
        rng = random.Random(1)
        times = generate_send_times(
            self.window_start, self.window_end, max_count=6,
            min_gap_seconds=60, max_gap_seconds=600, rng=rng,
        )
        gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
        self.assertGreater(len(set(gaps)), 1, f"gaps should vary, got constant {gaps}")

    def test_short_window_returns_fewer_than_requested(self):
        short_end = self.window_start + timedelta(minutes=5)
        rng = random.Random(3)
        times = generate_send_times(
            self.window_start, short_end, max_count=100,
            min_gap_seconds=60, max_gap_seconds=120, rng=rng,
        )
        self.assertLess(len(times), 100)
        self.assertGreater(len(times), 0)
        for t in times:
            self.assertLess(t, short_end)

    def test_hourly_limit_is_never_exceeded_in_any_rolling_hour_bucket(self):
        rng = random.Random(11)
        times = generate_send_times(
            self.window_start, self.window_end, max_count=50,
            min_gap_seconds=30, max_gap_seconds=120,
            hourly_limit=5, rng=rng,
        )
        # Bucket by the same rolling-hour-from-window-start logic the
        # implementation uses, and confirm no bucket exceeds the limit.
        bucket_start = self.window_start
        count = 0
        for t in times:
            if t - bucket_start >= timedelta(hours=1):
                bucket_start = t
                count = 0
            count += 1
            self.assertLessEqual(count, 5, f"hourly_limit violated at {t}")

    def test_hourly_limit_reduces_total_yield_vs_no_limit(self):
        rng_a = random.Random(99)
        rng_b = random.Random(99)
        unlimited = generate_send_times(
            self.window_start, self.window_end, max_count=200,
            min_gap_seconds=30, max_gap_seconds=60, rng=rng_a,
        )
        limited = generate_send_times(
            self.window_start, self.window_end, max_count=200,
            min_gap_seconds=30, max_gap_seconds=60, hourly_limit=3, rng=rng_b,
        )
        self.assertLess(len(limited), len(unlimited))

    def test_deterministic_given_seeded_rng(self):
        times_a = generate_send_times(
            self.window_start, self.window_end, max_count=10,
            min_gap_seconds=60, max_gap_seconds=300, rng=random.Random(555),
        )
        times_b = generate_send_times(
            self.window_start, self.window_end, max_count=10,
            min_gap_seconds=60, max_gap_seconds=300, rng=random.Random(555),
        )
        self.assertEqual(times_a, times_b)


if __name__ == "__main__":
    unittest.main()
