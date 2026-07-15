#!/usr/bin/env bash
# Runtime startup sequence for the backend container:
#   1. Block until Postgres is genuinely reachable (see wait_for_db.py for why
#      depends_on's healthcheck gate alone isn't sufficient).
#   2. Apply migrations.
#   3. Hand off to the real process (uvicorn, passed in as CMD) via exec, so
#      it becomes PID 1 and receives signals directly (clean shutdown).
set -euo pipefail

echo "[entrypoint] waiting for database..."
python -m app.wait_for_db

echo "[entrypoint] running migrations..."
alembic upgrade head
echo "[entrypoint] migrations complete"

echo "[entrypoint] starting application..."
exec "$@"
