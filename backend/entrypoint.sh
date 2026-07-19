#!/usr/bin/env bash
# Runtime startup sequence for the backend container:
#   1. Block until Postgres is genuinely reachable (see wait_for_db.py for why
#      depends_on's healthcheck gate alone isn't sufficient).
#   2. Apply migrations - serialized across every container that runs this
#      same entrypoint (backend + all six workers) via a Postgres advisory
#      lock, so only one container is ever running real migration DDL at a
#      time; see migrate_with_lock.py's own docstring for the concurrent
#      CREATE TABLE/CREATE TYPE race this closes (surfaced during M7.1
#      verification - a plain `alembic upgrade head` with no serialization
#      let two containers race the same DDL statement).
#   3. Hand off to the real process (uvicorn, passed in as CMD) via exec, so
#      it becomes PID 1 and receives signals directly (clean shutdown).
set -euo pipefail

echo "[entrypoint] waiting for database..."
python -m app.wait_for_db

echo "[entrypoint] running migrations..."
python -m app.migrate_with_lock
echo "[entrypoint] migrations complete"

echo "[entrypoint] starting application..."
exec "$@"
