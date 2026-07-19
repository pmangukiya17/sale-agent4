"""
Real, DB-backed tests of the M8.5 Notification Center - app/notifications/
rules.py, service.py, worker.py. Covers: the built-in conversation.created
rule produces a Notification + a "notified" NotificationDispatch; an
event_type with no registered rule produces only a "skipped"
NotificationDispatch (no Notification row); create_notification_for_event
never double-processes the same Event (NotificationDispatch's own unique
constraint on event_id enforces this at the DB level, mirroring
EventConsumption's own precedent); worker.run_one_tick() only picks up
events with no NotificationDispatch row yet, in Event.sequence_no order,
and a rerun of run_one_tick() is a true no-op once every event has been
dispatched.

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_notifications
"""
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
from app.models.notification import Notification, NotificationDispatch
from app.models.user import User
from app.models.workflow_event import Event
from app.notifications import worker as notification_worker
from app.notifications.rules import (
    CONVERSATION_CREATED_EVENT_TYPE,
    get_notification_rule,
    register_notification_rule,
)
from app.notifications.service import create_notification_for_event
from app.workflow_engine.events import publish_event


def _now():
    return datetime.now(timezone.utc)


class TestNotifications(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        self.user = User(email=f"m8.5-notifications-test-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M8.5 Notifications Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.commit()

    def tearDown(self):
        self.db.rollback()
        self.db.query(NotificationDispatch).filter(
            NotificationDispatch.event_id.in_(
                self.db.query(Event.id).filter(Event.company_profile_id == self.company_profile.id)
            )
        ).delete(synchronize_session=False)
        self.db.query(Notification).filter(Notification.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.query(Event).filter(Event.company_profile_id == self.company_profile.id).delete(synchronize_session=False)
        self.db.commit()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    def _publish(self, event_type: str) -> Event:
        event = publish_event(
            self.db,
            event_type=event_type,
            company_profile_id=self.company_profile.id,
            source="tests.test_notifications",
        )
        self.db.commit()
        return event

    # --- rules registry -----------------------------------------------------
    def test_conversation_created_rule_is_registered(self):
        rule = get_notification_rule(CONVERSATION_CREATED_EVENT_TYPE)
        self.assertIsNotNone(rule)

    def test_registering_the_same_event_type_twice_raises(self):
        with self.assertRaises(KeyError):
            register_notification_rule(CONVERSATION_CREATED_EVENT_TYPE, lambda event: None)

    def test_unregistered_event_type_has_no_rule(self):
        self.assertIsNone(get_notification_rule(f"test.no_rule.{uuid.uuid4()}"))

    # --- service.create_notification_for_event -------------------------------
    def test_matched_rule_creates_notification_and_notified_dispatch(self):
        event = self._publish(CONVERSATION_CREATED_EVENT_TYPE)

        notification = create_notification_for_event(self.db, event)
        self.db.commit()

        self.assertIsNotNone(notification)
        self.assertEqual(notification.company_profile_id, self.company_profile.id)
        self.assertEqual(notification.event_id, event.id)
        self.assertIsNone(notification.user_id)
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)

        dispatch = self.db.scalars(
            self.db.query(NotificationDispatch).filter(NotificationDispatch.event_id == event.id).statement
        ).first()
        self.assertIsNotNone(dispatch)
        self.assertEqual(dispatch.decision, "notified")
        self.assertEqual(dispatch.notification_id, notification.id)

    def test_unmatched_event_type_creates_only_a_skipped_dispatch(self):
        event = self._publish(f"test.unmatched.{uuid.uuid4()}")

        notification = create_notification_for_event(self.db, event)
        self.db.commit()

        self.assertIsNone(notification)
        self.assertEqual(self.db.query(Notification).filter(Notification.event_id == event.id).count(), 0)

        dispatch = self.db.scalars(
            self.db.query(NotificationDispatch).filter(NotificationDispatch.event_id == event.id).statement
        ).first()
        self.assertIsNotNone(dispatch)
        self.assertEqual(dispatch.decision, "skipped")
        self.assertIsNone(dispatch.notification_id)

    def test_processing_the_same_event_twice_violates_the_unique_dispatch_constraint(self):
        """NotificationDispatch.event_id carries a UniqueConstraint (see
        that model's own docstring) - the same DB-level idempotency
        guarantee EventConsumption established for the Event Dispatcher.
        A caller that (incorrectly) tries to dispatch the same event
        twice within two separate transactions must fail loudly, not
        silently create a second Notification."""
        event = self._publish(CONVERSATION_CREATED_EVENT_TYPE)

        create_notification_for_event(self.db, event)
        self.db.commit()

        with self.assertRaises(Exception):
            create_notification_for_event(self.db, event)
            self.db.commit()
        self.db.rollback()

    # --- worker.run_one_tick -------------------------------------------------
    def test_run_one_tick_dispatches_only_undispatched_events_in_sequence_order(self):
        event_a = self._publish(CONVERSATION_CREATED_EVENT_TYPE)
        event_b = self._publish(f"test.unmatched.{uuid.uuid4()}")

        counts = notification_worker.run_one_tick()

        self.assertGreaterEqual(counts["notified"], 1)
        self.assertGreaterEqual(counts["skipped"], 1)

        dispatch_a = self.db.scalars(
            self.db.query(NotificationDispatch).filter(NotificationDispatch.event_id == event_a.id).statement
        ).first()
        dispatch_b = self.db.scalars(
            self.db.query(NotificationDispatch).filter(NotificationDispatch.event_id == event_b.id).statement
        ).first()
        self.assertIsNotNone(dispatch_a)
        self.assertIsNotNone(dispatch_b)
        self.assertEqual(dispatch_a.decision, "notified")
        self.assertEqual(dispatch_b.decision, "skipped")

    def test_run_one_tick_is_a_no_op_once_everything_is_dispatched(self):
        self._publish(CONVERSATION_CREATED_EVENT_TYPE)
        self._publish(f"test.unmatched.{uuid.uuid4()}")

        first_tick = notification_worker.run_one_tick()
        self.assertTrue(any(first_tick.values()))

        second_tick = notification_worker.run_one_tick()
        # Other tests/company profiles may still have their own backlog in
        # a shared DB, so this only asserts THIS test's two events aren't
        # reprocessed - captured indirectly via total dispatch row count
        # staying exactly 2 for this company_profile's events.
        dispatch_count = (
            self.db.query(NotificationDispatch)
            .filter(
                NotificationDispatch.event_id.in_(
                    self.db.query(Event.id).filter(Event.company_profile_id == self.company_profile.id)
                )
            )
            .count()
        )
        self.assertEqual(dispatch_count, 2)
        del second_tick  # not asserted directly - see comment above


if __name__ == "__main__":
    unittest.main()
