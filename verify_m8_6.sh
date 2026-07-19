#!/usr/bin/env bash
# Verification for M8.6 (Real-Time Event Streaming) against your real
# Docker environment.
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_*.sh before it. M8.6 adds NO new tables/
# migrations and NO new docker-compose service (the poller runs inside
# the existing `backend` service's own process - see
# app/realtime/__init__.py's own docstring for why that's structural) -
# `docker compose up --build` is sufficient.
#
# What this script CANNOT verify (disclosed up front):
#   - Sustained, multi-minute live push behavior, and what a real
#     dropped-wifi/laptop-sleep reconnect actually looks like in a real
#     browser tab - step 6 below proves the SSE endpoint opens,
#     authenticates, and delivers at least one real event end-to-end via
#     `curl -N`, which is a genuine, scriptable proof of the whole chain
#     (ticket mint -> SSE connect -> poller picks up a real Event -> push
#     reaches the client) - but it is a short-lived, one-shot check, not
#     a soak test.
#   - The Notification bell's live update (useNotifications' stream-
#     triggered debounced refetch) and the manual reconnect-with-backoff
#     logic in useEventStream.ts were never exercised in a real browser
#     from this environment - only `tsc -b passes` was confirmed. Watch
#     the Network tab (an `event-stream` request that stays pending,
#     streaming `data:` frames) to confirm this visually.
#   - No live AI provider call is made anywhere in this script.
set -euo pipefail

echo "=== 1/8: rebuild + boot ==="
docker compose up --build -d
echo "waiting for backend to report healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null; then
    echo "backend is up"
    break
  fi
  sleep 2
done
curl -sf http://localhost:8000/api/v1/health && echo || { echo "FAILED: backend never became healthy - check: docker compose logs backend"; exit 1; }

echo
echo "=== 2/8: confirm the realtime poller actually started (logged once at startup by app.main's own lifespan) ==="
# Deliberately a retry loop, not a single fixed `sleep 2` + one grep
# attempt - the grep pattern itself was never the problem (it's an exact,
# unambiguous substring of the real log line, unlike step 3's checks
# below). The actual bug was a race: /api/v1/health starts responding as
# soon as FastAPI's lifespan reaches its `yield`, which happens the
# instant realtime_poller.start() RETURNS - and start() only calls
# asyncio.create_task(_run_forever()), which SCHEDULES that coroutine
# without running any of it yet (see poller.py's own start()/
# _run_forever()). "Realtime poller starting" is only logged after
# _run_forever() actually gets a turn on the event loop and finishes
# _initialize_watermark()'s own DB round trip - a real, if usually short,
# window where the health check can already be green before that log
# line exists. A single `sleep 2` assumed that window was always shorter
# than 2s; polling for up to 20s (same shape as step 1's own health-check
# retry loop) is what actually tolerates it.
for i in $(seq 1 10); do
  if docker compose logs backend | grep -q "Realtime poller starting"; then
    echo "confirmed: Realtime poller started inside the backend process"
    break
  fi
  if [ "$i" -eq 10 ]; then
    echo "FAILED: did not find the Realtime poller startup log line after 20s - check: docker compose logs backend"; exit 1
  fi
  sleep 2
done

echo
echo "=== 3/8: layering boundary matrix (M8.6) ==="
echo "-- app/realtime/ must never import a concrete domain package --"
if docker compose exec -T backend grep -rlE "^\s*(from|import)\s+app\.(discovery|research|personalization|outreach|delivery|reply_intelligence|workflow_engine|workflow_actions|supervisor|ai_agents|ai_gateway|notifications)" app/realtime/; then
  echo "FAILED: app.realtime imports a concrete domain package (or app.notifications) - it must stay a pure, generic Event consumer"; exit 1
fi
echo "-- app/realtime/ must never construct an Event or call publish_event() (same false-positive-safe check as verify_m8_5.sh's own step 3 - see that script's own comment for why this isn't a bare substring grep) --"
if docker compose exec -T backend grep -rlP --include='*.py' '\bpublish_event\((?!\))|\bEvent\((?!\))' app/realtime/; then
  echo "FAILED: app.realtime appears to construct/publish an Event itself"; exit 1
fi
echo "-- app/notifications/ must still never publish a second-order Event (Decision 7 - Notifications remain a presentation concern, not a business fact) --"
if docker compose exec -T backend grep -rE "notification\.created|publish_event" app/notifications/*.py | grep -v "__pycache__"; then
  echo "FAILED: app.notifications appears to publish an Event - Decision 7 explicitly rules this out"; exit 1
fi
echo "-- no LISTEN/NOTIFY anywhere in the backend (Decision 6 - server-side polling only, no second operational pattern) --"
# Deliberately NOT a bare "LISTEN |NOTIFY " substring grep - this
# package's own docstrings (app/core/config.py, app/realtime/poller.py)
# explain in prose exactly why LISTEN/NOTIFY was NOT used, and phrases
# like "Postgres LISTEN/NOTIFY - an explicit..." or "NOTIFY remains a
# valid..." contain "NOTIFY " (the word, followed by a space and another
# word) with the exact same shape a bare substring match is looking for -
# a false positive, not real usage (same class of bug as verify_m8_5.sh's
# own step 3 fix - see that script's comment for the precedent). Verified
# by hand: neither file contains LISTEN/NOTIFY inside an actual executed
# SQL string or a pg_notify() call - every hit is prose mentioning the
# words while explaining their absence.
# The fix: genuine LISTEN/NOTIFY usage in this codebase could only ever
# appear as a quoted SQL string literal being executed (e.g.
# `text("LISTEN events_channel")`, `cursor.execute("NOTIFY ...")`) or a
# call to the pg_notify() SQL function - i.e. immediately preceded by a
# quote character, or spelled as `pg_notify(`. Prose in a docstring/
# comment never has a quote character directly adjacent to the word on
# the same line, so this distinguishes "the code actually does this" from
# "the code explains that it deliberately doesn't".
if docker compose exec -T backend grep -rniE --include='*.py' '["'"'"']\s*(LISTEN|NOTIFY)\b|pg_notify\s*\(' app/; then
  echo "FAILED: found LISTEN/NOTIFY usage - Decision 6 explicitly rules this out for M8.6"; exit 1
fi
echo "confirmed: every M8.6 layering boundary and architectural decision holds"

echo
echo "=== 4/8: M8.6 Real-Time Streaming test suite (real DB, real Postgres for the poller test; the ticket/broadcaster tests need no DB at all) ==="
docker compose exec -T backend python -m unittest tests.test_realtime_tickets tests.test_realtime_broadcaster tests.test_realtime_poller -v

echo
echo "=== 5/8: M8.5 Notification Center regression - proves the M8.6 addition didn't disturb Notifications ==="
docker compose exec -T backend python -m unittest tests.test_notifications -v

echo
echo "=== 6/8: end-to-end SSE smoke test (needs FIRST_ADMIN_EMAIL/FIRST_ADMIN_PASSWORD from your .env) ==="
TOKEN=$(curl -sf -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${FIRST_ADMIN_EMAIL:-admin@example.com}&password=${FIRST_ADMIN_PASSWORD:-changeme}" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])") || {
  echo "SKIPPED: could not log in with FIRST_ADMIN_EMAIL/FIRST_ADMIN_PASSWORD - set them in your shell to run steps 6-8"; TOKEN=""; }

if [ -n "$TOKEN" ]; then
  COMPANY_ID=$(curl -sf http://localhost:8000/api/v1/company-profiles \
    -H "Authorization: Bearer $TOKEN" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d[0]['id'] if d else '')")
  if [ -n "$COMPANY_ID" ]; then
    echo "-- mint a stream ticket (normal Bearer auth) --"
    TICKET=$(curl -sf -X POST "http://localhost:8000/api/v1/company-profiles/$COMPANY_ID/event-stream/ticket" \
      -H "Authorization: Bearer $TOKEN" | python3 -c "import sys, json; print(json.load(sys.stdin)['ticket'])")
    echo "ticket minted"

    echo "-- open the stream in the background, publish a real Event, confirm it arrives --"
    curl -N -s "http://localhost:8000/api/v1/company-profiles/$COMPANY_ID/event-stream?ticket=$TICKET" > /tmp/m8_6_stream_output.txt &
    CURL_PID=$!
    sleep 1

    echo "-- publish a real conversation.created-shaped test Event via the same publish_event() every other caller uses --"
    docker compose exec -T backend python -c "
from app.db.session import SessionLocal
from app.workflow_engine.events import publish_event
db = SessionLocal()
publish_event(db, event_type='test.m8_6_smoke', company_profile_id='$COMPANY_ID', source='verify_m8_6.sh')
db.commit()
db.close()
print('published test.m8_6_smoke')
"
    sleep 3
    kill "$CURL_PID" 2>/dev/null || true
    wait "$CURL_PID" 2>/dev/null || true

    echo
    echo "-- stream output received --"
    cat /tmp/m8_6_stream_output.txt
    if grep -q "test.m8_6_smoke" /tmp/m8_6_stream_output.txt; then
      echo
      echo "CONFIRMED: the published Event was received over the live SSE connection end-to-end."
    else
      echo "FAILED: the SSE connection did not deliver the test Event within the wait window - check: docker compose logs backend"; exit 1
    fi
    rm -f /tmp/m8_6_stream_output.txt
  else
    echo "SKIPPED: no company profile exists yet for this admin user - create one in the app first to exercise steps 6-8"
  fi
fi

echo
echo "=== 7/8: reconnect/backlog replay smoke test (since_sequence) ==="
if [ -n "${TOKEN:-}" ] && [ -n "${COMPANY_ID:-}" ]; then
  TICKET2=$(curl -sf -X POST "http://localhost:8000/api/v1/company-profiles/$COMPANY_ID/event-stream/ticket" \
    -H "Authorization: Bearer $TOKEN" | python3 -c "import sys, json; print(json.load(sys.stdin)['ticket'])")
  echo "-- requesting backlog since_sequence=0 - should immediately replay this workspace's Event history, including the smoke-test Event above, before going idle --"
  timeout 3 curl -N -s "http://localhost:8000/api/v1/company-profiles/$COMPANY_ID/event-stream?ticket=$TICKET2&since_sequence=0" | head -20 || true
  echo "(inspect the output above by eye - it should contain at least one 'data:' line with a real Event, not just keep-alive comments)"
else
  echo "SKIPPED: depends on step 6's TOKEN/COMPANY_ID"
fi

echo
echo "=== 8/8: SQLAlchemy mapper configuration (M8.6 added zero models/migrations, so this should be an unaffected no-op check) ==="
docker compose exec -T backend python -c "
from app.db import base as _base
from sqlalchemy.orm import configure_mappers
configure_mappers()
print('All mappers configured successfully - every relationship() resolved.')
"

echo
echo "ALL CHECKS COMPLETE"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - No sustained/soak test of the live connection, and no real-browser confirmation of the Notification bell's"
echo "    stream-triggered refresh or useEventStream.ts's manual reconnect-with-backoff - see this script's own header."
echo "  - AI Workforce and Activity Timeline are NOT wired to live-update in this milestone - their underlying data"
echo "    (WorkflowInstance, Prospect timestamps) does not flow through the Event stream yet; wiring them honestly"
echo "    requires those domains to first publish real Events, which remains the same deferred retrofit M8.5's own"
echo "    Decision 6 already called out (Discovery/Research/Personalization/Outreach/Delivery/Workflow Engine)."
echo "  - Postgres LISTEN/NOTIFY remains a disclosed, deliberate future upgrade path if 1.5s polling ever becomes a"
echo "    measurable bottleneck - not introduced now, per Decision 6."
