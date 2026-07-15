"""
Block until Postgres is actually reachable, retrying with bounded backoff.

Why this exists: docker-compose's `depends_on: condition: service_healthy`
only guarantees that the "db" container itself passed its healthcheck at
some point before "backend" was started — it does NOT guarantee that the
"db" hostname is resolvable, or that Postgres is accepting connections,
at the exact instant this container's entrypoint runs. Docker's embedded
DNS registration and Postgres's own startup (which restarts once
internally after initdb on a brand-new volume) both have a brief window
where a single connection attempt can fail. Without a retry loop, that
one bad instant crashes the whole container instead of resolving itself
half a second later.

psycopg2.connect() performs hostname resolution as its first step, so a
DNS-not-ready condition and a Postgres-not-ready condition both surface
as psycopg2.OperationalError here and are retried identically.
"""
import sys
import time

import psycopg2

from app.core.config import settings

MAX_ATTEMPTS = 30
INITIAL_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 10.0


def wait_for_db() -> None:
    delay = INITIAL_DELAY_SECONDS

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            conn = psycopg2.connect(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                dbname=settings.POSTGRES_DB,
                connect_timeout=5,
            )
            conn.close()
            print(f"[wait_for_db] database reachable after {attempt} attempt(s)", flush=True)
            return
        except psycopg2.OperationalError as exc:
            message = str(exc).strip()
            print(f"[wait_for_db] attempt {attempt}/{MAX_ATTEMPTS} failed: {message}", flush=True)
            if attempt == MAX_ATTEMPTS:
                print("[wait_for_db] giving up — database never became reachable", flush=True)
                sys.exit(1)
            time.sleep(delay)
            delay = min(delay * 1.5, MAX_DELAY_SECONDS)


if __name__ == "__main__":
    wait_for_db()
