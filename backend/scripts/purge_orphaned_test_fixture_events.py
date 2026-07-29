"""
ONE-TIME, MANUAL data-hygiene script - not part of any automated test or
migration, not wired into any worker or route. Written for the CEO review
round dated 2026-07-28 that traced test_poll_once_fans_out_a_new_event_to_
the_right_subscriber / test_poll_once_does_not_redispatch_the_same_event_
twice (tests/test_realtime_poller.py) timing out on
`asyncio.wait_for(queue.get(), timeout=2)`.

ROOT CAUSE (confirmed, not a regression from the event/notification
ownership fix - see this project's own writeup in
verify_m8_3_step6_gateway_diagnostics.sh and the FK-violation fix commits
for the full history):

app/realtime/poller.py's `_fetch_new_events_sync()` queries `events` GLOBALLY
(no company_profile_id scope), `ORDER BY sequence_no ASC LIMIT
REALTIME_STREAM_POLL_BATCH_SIZE` (200), and only adds a `WHERE sequence_no >
last_seen` filter when `last_seen is not None`. In the real running
application this is always safe: `_run_forever()` calls
`_initialize_watermark()` (which sets the watermark to `MAX(sequence_no)`)
before the poll loop ever starts, so `poll_once()` is NEVER actually invoked
with `last_seen=None` in production. tests/test_realtime_poller.py's own
setUp()/tearDown() are the ONLY call site in this codebase that deliberately
resets `poller._last_seen_sequence_no = None` (a test-isolation
convenience, to stop one test's watermark leaking into the next) - which
means those two tests silently depended on an unstated invariant: the total
number of rows ever left in `events` had to be smaller than
REALTIME_STREAM_POLL_BATCH_SIZE (200), or the "oldest 200 rows in all of
history" query would never reach whatever this test just published.

That invariant held for a long time by accident, then broke: this shared,
persistent Postgres database has been accumulating orphaned `Event` rows for
an unknown span of time, specifically FROM every prior test run that hit the
exact ForeignKeyViolation-during-teardown race this whole review round fixed
(9 files, see event_backbone_cleanup.py / delete_events_and_dependents()).
Before that fix, a bare `Event` delete could raise mid-tearDown, aborting the
rest of that tearDown (CompanyProfile/User never got deleted either) and
leaving that test's own Event rows in the table permanently. Confirmed via
`git diff` that app/realtime/poller.py and app/realtime/broadcaster.py
themselves have ZERO changes in this fix - the watermark mechanism, the
publish path, and subscriber registration are byte-for-byte unchanged.

This script is the safe, one-time remediation: every CompanyProfile these 9
test files (plus test_research_workflow_e2e.py) ever create is named with a
recognizable, disposable, test-only fixture pattern - it always ends in
"Test Co" (e.g. "M7.1 Dispatcher Test Co", "M8.6 Poller Test Co", "M8.13
Research E2E Test Co"...) - a pattern no real production CompanyProfile
would ever collide with. For every CompanyProfile matching that pattern,
this script runs the EXACT SAME dependent-first delete order
delete_events_and_dependents() already uses (EventConsumption /
NotificationDispatch / Notification, then Event), then removes the
CompanyProfile/owning User themselves - i.e., it retroactively finishes the
tearDown that should have completed on every one of those historical runs,
using the same helper this fix already proved correct. It does NOT touch
poller.py, does NOT touch any test file, and does NOT touch any real
(non-"Test Co") CompanyProfile.

Run once, inside the backend container, against the real Postgres:
    docker compose exec -T backend python -m scripts.purge_orphaned_test_fixture_events

Safe to run more than once (idempotent - matches zero rows once the backlog
is gone). After running, test_realtime_poller.py's two previously-hanging
tests should pass again on the very next run, since `events` no longer has
a multi-hundred-row historical prefix ahead of whatever a fresh test
publishes.
"""
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.models.company_profile import CompanyProfile
from app.models.user import User
from tests.event_backbone_cleanup import delete_events_and_dependents

_TEST_FIXTURE_NAME_SUFFIX = "Test Co"


def main() -> None:
    db = SessionLocal()
    try:
        candidates = db.query(CompanyProfile).filter(CompanyProfile.name.like(f"%{_TEST_FIXTURE_NAME_SUFFIX}")).all()
        print(f"Found {len(candidates)} orphaned test-fixture CompanyProfile row(s) matching '%{_TEST_FIXTURE_NAME_SUFFIX}'.")

        purged = 0
        skipped = 0
        for profile in candidates:
            owner_user_id = profile.owner_user_id
            try:
                delete_events_and_dependents(db, company_profile_id=profile.id)
                db.query(CompanyProfile).filter(CompanyProfile.id == profile.id).delete()
                db.commit()
                if owner_user_id is not None:
                    db.query(User).filter(User.id == owner_user_id).delete()
                    db.commit()
                purged += 1
            except Exception as exc:  # noqa: BLE001 - report and continue; a row with OTHER live FKs
                # (e.g. a WorkflowInstance/Prospect this specific test class
                # also leaked) needs its own investigation, not a silent
                # blanket delete - skip it and move on rather than half-
                # deleting or masking a different problem.
                db.rollback()
                print(f"  SKIPPED {profile.id} ({profile.name!r}): {exc}")
                skipped += 1

        print(f"Purged {purged} orphaned test-fixture CompanyProfile(s) and their Event backlog. Skipped {skipped}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
