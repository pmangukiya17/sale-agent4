"""
Real, DB-backed tests of app/workflow_engine/events.py's publish_event()
- M7.1 Part 1, Phase 1. Proves the transactional-outbox contract the
approved architecture requires: a published event is visible only once
the CALLER's own transaction commits, and a caller rollback rolls the
event back too - there is no separate connection, no separate commit,
and no way for the event to be lost or duplicated relative to whatever
domain write it's reporting.

No real domain module calls publish_event() yet in this phase - these
tests are the only caller, using a throwaway CompanyProfile/User fixture,
matching test_conversation_resolver.py's own "test the primitive in
isolation, not through a full fixture chain" precedent from M6.3.

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_workflow_events
"""
import unittest
import uuid
from datetime import datetime, timedelta, timezone

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.models.company_profile import CompanyProfile
from app.models.enums import UserRole
from app.models.user import User
from app.models.workflow_event import Event
from app.workflow_engine.events import publish_event
from tests.event_backbone_cleanup import delete_events_and_dependents


def _now():
    return datetime.now(timezone.utc)


class TestPublishEvent(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        self.user = User(email=f"m7.1-events-test-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M7.1 Events Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.commit()

    def tearDown(self):
        self.db.rollback()
        # Generalized fix (CEO review, 2026-07-28 - see
        # test_research_workflow_e2e.py's own tearDown for the full
        # writeup): a real, always-on notification worker container polls
        # `events` independently of this test, and inserts a
        # NotificationDispatch row (decision="skipped" for these
        # synthetic test.* event types, but still a row referencing this
        # Event) for ANY committed Event - a bare Event delete can race
        # it. delete_events_and_dependents() deletes the complete
        # dependent set (EventConsumption/Notification/NotificationDispatch)
        # before the Event delete itself.
        delete_events_and_dependents(self.db, company_profile_id=self.company_profile.id)
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    # --- basic round trip ----------------------------------------------------
    def test_publish_event_creates_a_row_with_correct_fields(self):
        subject_id = uuid.uuid4()
        correlation_id = uuid.uuid4()
        causation_id = uuid.uuid4()

        event = publish_event(
            self.db,
            event_type="test.thing.happened",
            company_profile_id=self.company_profile.id,
            source="tests.test_workflow_events",
            subject_type="test_subject",
            subject_id=subject_id,
            payload={"foo": "bar", "count": 3},
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        self.db.commit()

        fetched = self.db.get(Event, event.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.event_type, "test.thing.happened")
        self.assertEqual(fetched.company_profile_id, self.company_profile.id)
        self.assertEqual(fetched.source, "tests.test_workflow_events")
        self.assertEqual(fetched.subject_type, "test_subject")
        self.assertEqual(fetched.subject_id, subject_id)
        self.assertEqual(fetched.payload, {"foo": "bar", "count": 3})
        self.assertEqual(fetched.correlation_id, correlation_id)
        self.assertEqual(fetched.causation_id, causation_id)
        self.assertEqual(fetched.schema_version, 1)
        self.assertIsNotNone(fetched.sequence_no)

    def test_occurred_at_defaults_to_now_when_not_provided(self):
        before = _now()
        event = publish_event(
            self.db, event_type="test.no.timestamp", company_profile_id=self.company_profile.id, source="tests"
        )
        self.db.commit()
        after = _now()

        fetched = self.db.get(Event, event.id)
        self.assertGreaterEqual(fetched.occurred_at, before - timedelta(seconds=1))
        self.assertLessEqual(fetched.occurred_at, after + timedelta(seconds=1))

    def test_optional_fields_default_to_none(self):
        event = publish_event(
            self.db, event_type="test.minimal", company_profile_id=self.company_profile.id, source="tests"
        )
        self.db.commit()

        fetched = self.db.get(Event, event.id)
        self.assertIsNone(fetched.subject_type)
        self.assertIsNone(fetched.subject_id)
        self.assertIsNone(fetched.payload)
        self.assertIsNone(fetched.correlation_id)
        self.assertIsNone(fetched.causation_id)

    # --- ordering ---------------------------------------------------------
    def test_sequence_no_is_monotonically_increasing(self):
        first = publish_event(self.db, event_type="test.order.1", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()
        second = publish_event(self.db, event_type="test.order.2", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()
        third = publish_event(self.db, event_type="test.order.3", company_profile_id=self.company_profile.id, source="tests")
        self.db.commit()

        self.assertLess(first.sequence_no, second.sequence_no)
        self.assertLess(second.sequence_no, third.sequence_no)

    # --- the transactional-outbox contract itself --------------------------
    def test_event_is_not_visible_to_another_session_before_commit(self):
        event = publish_event(
            self.db, event_type="test.not.yet.committed", company_profile_id=self.company_profile.id, source="tests"
        )
        # Deliberately NOT committed yet.

        other_session = SessionLocal()
        try:
            fetched = other_session.get(Event, event.id)
            self.assertIsNone(fetched, "an uncommitted event must not be visible to a different session/connection")
        finally:
            other_session.close()

        # Clean up by committing now (tearDown's cleanup query needs the row to exist).
        self.db.commit()

    def test_rollback_of_callers_transaction_also_rolls_back_the_event(self):
        event = publish_event(
            self.db, event_type="test.will.be.rolled.back", company_profile_id=self.company_profile.id, source="tests"
        )
        event_id = event.id

        self.db.rollback()

        other_session = SessionLocal()
        try:
            fetched = other_session.get(Event, event_id)
            self.assertIsNone(fetched, "rolling back the caller's transaction must roll back the published event too")
        finally:
            other_session.close()

    def test_event_is_published_atomically_alongside_a_domain_write_in_the_same_transaction(self):
        # Simulates a real call site (Phase 8, later): a domain write and
        # an event published in the same transaction, both committed or
        # both rolled back together - never one without the other.
        new_user = User(email=f"m7.1-events-domain-write-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.OPERATOR)
        self.db.add(new_user)
        self.db.flush()

        event = publish_event(
            self.db,
            event_type="test.domain.write.happened",
            company_profile_id=self.company_profile.id,
            source="tests",
            subject_type="user",
            subject_id=new_user.id,
        )

        self.db.rollback()

        other_session = SessionLocal()
        try:
            self.assertIsNone(other_session.get(User, new_user.id), "the domain write must be rolled back too")
            self.assertIsNone(other_session.get(Event, event.id), "the event must be rolled back with it")
        finally:
            other_session.close()


if __name__ == "__main__":
    unittest.main()
