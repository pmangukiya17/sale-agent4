#!/usr/bin/env bash
# Verification for M8.5 (Event Backbone & Notification Center) against
# your real Docker environment.
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_*.sh before it. M8.5 adds two new migrations
# (0016_event_actor_severity_category, 0017_notifications) and one new
# docker-compose service (notification_worker) - `docker compose up
# --build` picks both up; migrations run automatically via the
# backend/worker image's existing entrypoint.sh (wait-for-db -> alembic
# upgrade head -> exec "$@"), same as every prior milestone.
#
# What this script CANNOT verify (disclosed up front):
#   - No existing domain module (Discovery/Research/Personalization/
#     Outreach/Delivery) publishes an Event yet beyond Reply
#     Intelligence's own pre-existing conversation.created publisher -
#     per your own approved Decision 6, retrofitting publish_event()
#     calls across those modules is explicitly a FUTURE milestone, not
#     M8.5. This script's end-to-end proof therefore exercises
#     conversation.created only (the one event_type this platform
#     already publishes for real), not a synthetic/fabricated one.
#   - The Activity Timeline / AI Workforce dashboard widgets still read
#     their own underlying tables directly - migrating them to consume
#     GET /company-profiles/{id}/events instead is explicitly deferred,
#     per the same Decision 6.
#   - No live AI provider call is made anywhere in this script.
#   - No browser-based verification of the notification bell's visual
#     appearance (badge dot, dropdown, mark-read/mark-all-read
#     interaction) - the frontend changes pass `tsc -b` cleanly (already
#     confirmed) but were never rendered/clicked in a real browser from
#     this environment, same disclosed limitation as every prior
#     frontend milestone.
set -euo pipefail

echo "=== 1/7: rebuild + boot ==="
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
echo "=== 2/7: notification_worker service is present and running ==="
if ! docker compose ps notification_worker | grep -q "Up\|running"; then
  echo "FAILED: notification_worker service is not running - check: docker compose logs notification_worker"; exit 1
fi
echo "confirmed: notification_worker is up"

echo
echo "=== 3/7: layering boundary matrix (M8.5) ==="
echo "-- app/notifications/ must never import a concrete domain package (Discovery/Research/Personalization/Outreach/Delivery/Reply Intelligence/Workflow Engine) - it only reacts to plain event_type strings --"
if docker compose exec -T backend grep -rlE "^\s*(from|import)\s+app\.(discovery|research|personalization|outreach|delivery|reply_intelligence|workflow_engine|workflow_actions|supervisor|ai_agents|ai_gateway)" app/notifications/; then
  echo "FAILED: app.notifications imports a concrete domain package - it must stay a pure, opaque Event consumer"; exit 1
fi
echo "-- app/notifications/ must never construct an Event or call publish_event() - Events are only ever created by their own domain's write path --"
# Deliberately NOT a bare substring grep for "publish_event|Event\(" - every
# file in this package documents the boundary it's honoring in its own
# docstring ("it never calls publish_event()", "the only sanctioned writer
# of an Event is ... publish_event()", etc.), and a bare substring match
# flags that prose as if it were a real call - a false positive, not an
# architecture violation (verified by hand: grepping for the real call
# shape "publish_event\([^)]" - i.e. an actual argument, since publish_event
# always requires `db` as its first positional arg - and for a real "Event("
# constructor both return zero matches in this package; every hit was
# "publish_event()", the bare, argument-less name mentioned in a comment).
# The fix: a real call/construction is never followed immediately by ")" -
# publish_event() always takes at least `db`, and Event() is only ever
# constructed with keyword args (see app/workflow_engine/events.py's own
# `Event(\n    event_type=...` shape) - so a negative lookahead for an
# immediately-adjacent close-paren distinguishes "the name is mentioned in
# prose" from "this is actually being called/constructed", without needing
# a full AST parse. --include='*.py' additionally keeps this from matching
# the docstring text baked into compiled __pycache__/*.pyc files.
if docker compose exec -T backend grep -rlP --include='*.py' '\bpublish_event\((?!\))|\bEvent\((?!\))' app/notifications/; then
  echo "FAILED: app.notifications appears to construct/publish an Event itself"; exit 1
fi
echo "-- app/api/routes/notifications.py must never construct a Notification directly - only the worker may --"
if docker compose exec -T backend grep -E "Notification\(" app/api/routes/notifications.py; then
  echo "FAILED: the notifications route constructs a Notification directly - only app.notifications.service may do this"; exit 1
fi
echo "-- app/api/routes/events.py must never construct an Event directly - read-only surface --"
if docker compose exec -T backend grep -E "Event\(" app/api/routes/events.py; then
  echo "FAILED: the events route constructs an Event directly - it must stay read-only"; exit 1
fi
echo "confirmed: every M8.5 layering boundary holds"

echo
echo "=== 4/7: M8.5 Notification Center test suite (real DB, real Postgres) ==="
docker compose exec -T backend python -m unittest tests.test_notifications -v

echo
echo "=== 5/7: M7.1 Event/Workflow Engine regression - proves the four new Event columns and the Notification tables didn't disturb the existing Event stream/dispatcher/step runner ==="
docker compose exec -T backend python -m unittest tests.test_workflow_events tests.test_event_dispatcher_worker tests.test_step_runner_worker tests.test_workflow_definitions tests.test_workflow_definition_validation tests.test_workflow_instance_models tests.test_action_registry tests.test_pilot_workflow_e2e -v

echo
echo "=== 6/7: SQLAlchemy mapper configuration - proves Notification/NotificationDispatch's relationship()s to Event/CompanyProfile/User all resolve, alongside every pre-existing model ==="
docker compose exec -T backend python -c "
from app.db import base as _base
from sqlalchemy.orm import configure_mappers
configure_mappers()
print('All mappers configured successfully - every relationship() resolved.')
"

echo
echo "=== 7/7: Events + Notifications read API smoke test (needs FIRST_ADMIN_EMAIL/FIRST_ADMIN_PASSWORD from your .env) ==="
echo "-- login --"
TOKEN=$(curl -sf -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${FIRST_ADMIN_EMAIL:-admin@example.com}&password=${FIRST_ADMIN_PASSWORD:-changeme}" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])") || {
  echo "SKIPPED: could not log in with FIRST_ADMIN_EMAIL/FIRST_ADMIN_PASSWORD - set them in your shell to run this step"; TOKEN=""; }

if [ -n "$TOKEN" ]; then
  COMPANY_ID=$(curl -sf http://localhost:8000/api/v1/company-profiles \
    -H "Authorization: Bearer $TOKEN" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d[0]['id'] if d else '')")
  if [ -n "$COMPANY_ID" ]; then
    echo "-- GET /company-profiles/$COMPANY_ID/events --"
    curl -sf "http://localhost:8000/api/v1/company-profiles/$COMPANY_ID/events?limit=5" -H "Authorization: Bearer $TOKEN" && echo
    echo "-- GET /company-profiles/$COMPANY_ID/notifications --"
    curl -sf "http://localhost:8000/api/v1/company-profiles/$COMPANY_ID/notifications?limit=5" -H "Authorization: Bearer $TOKEN" && echo
    echo "-- POST /company-profiles/$COMPANY_ID/notifications/mark-all-read --"
    curl -sf -X POST "http://localhost:8000/api/v1/company-profiles/$COMPANY_ID/notifications/mark-all-read" -H "Authorization: Bearer $TOKEN" && echo
  else
    echo "SKIPPED: no company profile exists yet for this admin user - create one in the app first to exercise this step"
  fi
fi

echo
echo "ALL CHECKS COMPLETE"
echo
echo "NOT covered by anything above - disclosed, deferred concerns (see header):"
echo "  - Only Reply Intelligence's pre-existing conversation.created publisher feeds real Notifications today;"
echo "    every other domain module publishing its own Events is explicitly future work (approved Decision 6)."
echo "  - Activity Timeline / AI Workforce dashboard widgets are not yet migrated to consume GET /events."
echo "  - The notification bell's real-browser appearance/interaction was never visually verified from this"
echo "    environment - only 'tsc -b passes' was confirmed."
