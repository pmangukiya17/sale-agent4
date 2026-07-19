"""
Serializes `alembic upgrade head` across every container that runs it on
boot (backend + all six workers - see entrypoint.sh's own docstring for
the full "single source of truth for startup" story) via a session-level
Postgres advisory lock held for the entire migration run.

Why this exists: entrypoint.sh's migration step has always run
independently in every one of this project's containers, every boot -
documented since M5 as "safe... whichever loses the race just finds
itself already at head and no-ops" (see docker-compose.yml's own
comment on the `worker` service). That statement is true for the *end
state* (Alembic does serialize on the alembic_version row's own UPDATE,
at the very end of a successful migration), but it was never true for
the DDL *inside* one - two containers can each independently observe
"migration X hasn't been applied yet" and then both attempt the SAME
CREATE TABLE/CREATE TYPE concurrently. Migration 0012 patched one
specific instance of this (an enum's CREATE TYPE racing under
checkfirst=True, replaced with an idempotent DO-block). Migration 0013
hit the identical CLASS of race on a plain, ordinary `op.create_table`
for the new `events` table (visible as `duplicate key value violates
unique constraint "pg_type_typname_nsp_index"` - Postgres implicitly
creates a pg_type row for every table's own composite row type, and two
concurrent CREATE TABLE statements for the same table name can lose that
race exactly the same way two concurrent CREATE TYPE statements can) -
surfaced now because M7.1 raised this project's concurrent-container
count from five to seven (two new workers), narrowing the already-rare
window further but not eliminating it.

Patching each individual racy DDL statement one at a time (another
DO-block, this time for CREATE TABLE) does not scale - every future
migration's every CREATE TABLE/CREATE TYPE would need the same
treatment, forever. This module fixes the actual root cause once,
for every current and future migration: only ONE container is ever
allowed to run `alembic upgrade head`'s real DDL at a time. Every other
container simply BLOCKS on the advisory lock (a genuine, efficient,
server-side wait - not a busy-retry loop) until the first one finishes
and releases it, then acquires the lock itself, finds nothing left
pending, and returns immediately. This makes the "harmless race"
docker-compose.yml already documented actually true at the DDL level,
not just at the alembic_version bookkeeping level.

Session-level (not transaction-level) advisory lock, held on a dedicated
psycopg2 connection kept open for the whole `alembic upgrade head`
subprocess call and released explicitly before this process exits -
and, defensively, released implicitly by Postgres the instant this
connection closes even if this process were to crash before reaching
the explicit unlock (session-level advisory locks are always released
at session end, unlike transaction-level ones, so there is no cleanup
path that can leave the lock permanently stuck).

The lock key (727271) is an arbitrary, fixed constant - it only needs to
be unique within this application's own namespace of advisory locks, of
which this is the only one in the codebase.
"""
import subprocess
import sys

import psycopg2

from app.core.config import settings

_MIGRATION_LOCK_KEY = 727271


def run_migrations_with_lock() -> None:
    conn = psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        dbname=settings.POSTGRES_DB,
        connect_timeout=10,
    )
    # Advisory lock functions take effect immediately regardless of
    # transaction state, but autocommit avoids leaving this connection
    # idle-in-transaction for the (potentially long, if this container
    # is the one actually applying pending migrations) duration of the
    # subprocess call below.
    conn.autocommit = True
    try:
        cursor = conn.cursor()
        print(
            f"[migrate_with_lock] acquiring advisory lock {_MIGRATION_LOCK_KEY} "
            "(blocks here if another container is already migrating - this is expected, not an error)...",
            flush=True,
        )
        cursor.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK_KEY,))
        print("[migrate_with_lock] lock acquired - running 'alembic upgrade head'", flush=True)

        result = subprocess.run(["alembic", "upgrade", "head"])

        cursor.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK_KEY,))
        print(f"[migrate_with_lock] lock released - alembic exited with code {result.returncode}", flush=True)

        if result.returncode != 0:
            sys.exit(result.returncode)
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations_with_lock()
