"""
Real, DB-backed tests of app/realtime/poller.py - M8.6. Covers: a newly
published Event is fanned out to BROADCASTER for the right
company_profile_id, the watermark advances so the same Event is never
dispatched twice, and _initialize_watermark() correctly starts from
"now" rather than replaying all of history to a fresh process.

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_realtime_poller
"""
import asyncio
import unittest
import uuid
from datetime import datetime, timezone

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.models.company_profile import CompanyProfile
from app.models.enums import UserRole
from app.models.user import User
from app.models.workflow_event import Event
from app.realtime import poller
from app.realtime.broadcaster import BROADCASTER
from app.workflow_engine.events import publish_event


def _now():
    return datetime.now(timezone.utc)


class TestRealtimePoller(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = SessionLocal()

        self.user = User(email=f"m8.6-poller-test-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M8.6 Poller Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.commit()

        # Isolate this test's watermark from whatever a previous test (or
        # a real running process) left behind - poll_once() only looks
        # at the module-level watermark, so each test starts from "no
        # events seen yet" and only ever publishes/observes its own.
        poller._last_seen_sequence_no = None  # noqa: SLF001 - intentional test-only reset, see module docstring

    def tearDown(self):
        self.db.rollback()
        self.db.query(Event).filter(Event.company_profile_id == self.company_profile.id).delete(synchronize_session=False)
        self.db.commit()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()
        poller._last_seen_sequence_no = None  # noqa: SLF001

    async def test_poll_once_fans_out_a_new_event_to_the_right_subscriber(self):
        queue = BROADCASTER.subscribe(self.company_profile.id)
        try:
            event = publish_event(
                self.db,
                event_type="test.poller.thing",
                company_profile_id=self.company_profile.id,
                source="tests.test_realtime_poller",
            )
            self.db.commit()

            dispatched = await poller.poll_once()
            self.assertGreaterEqual(dispatched, 1)

            payload = await asyncio.wait_for(queue.get(), timeout=2)
            self.assertEqual(payload["id"], str(event.id))
            self.assertEqual(payload["event_type"], "test.poller.thing")
        finally:
            BROADCASTER.unsubscribe(self.company_profile.id, queue)

    async def test_poll_once_does_not_redispatch_the_same_event_twice(self):
        queue = BROADCASTER.subscribe(self.company_profile.id)
        try:
            publish_event(
                self.db,
                event_type="test.poller.once_only",
                company_profile_id=self.company_profile.id,
                source="tests.test_realtime_poller",
            )
            self.db.commit()

            first_tick = await poller.poll_once()
            self.assertGreaterEqual(first_tick, 1)
            await asyncio.wait_for(queue.get(), timeout=2)

            second_tick = await poller.poll_once()
            self.assertEqual(second_tick, 0)
            self.assertTrue(queue.empty())
        finally:
            BROADCASTER.unsubscribe(self.company_profile.id, queue)

    async def test_initialize_watermark_starts_from_current_max_not_from_history(self):
        publish_event(
            self.db,
            event_type="test.poller.before_startup",
            company_profile_id=self.company_profile.id,
            source="tests.test_realtime_poller",
        )
        self.db.commit()

        await poller._initialize_watermark()  # noqa: SLF001 - exercising the real startup path directly

        queue = BROADCASTER.subscribe(self.company_profile.id)
        try:
            dispatched = await poller.poll_once()
            # The event published BEFORE _initialize_watermark() ran must
            # NOT be replayed - a fresh process only ever pushes what's
            # new from the moment it started (per-client catch-up is a
            # separate, per-request concern - see
            # app/api/routes/realtime.py's own since_sequence handling).
            self.assertEqual(dispatched, 0)
            self.assertTrue(queue.empty())
        finally:
            BROADCASTER.unsubscribe(self.company_profile.id, queue)


if __name__ == "__main__":
    unittest.main()
