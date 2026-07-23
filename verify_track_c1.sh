#!/usr/bin/env bash
# Track C1 (dashboard-capabilities-architecture-plan.md): Open
# Conversations KPI - a new GET .../conversations/count endpoint, backend
# tenant-isolation tests, and the frontend KPI card wired to it.
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_*.sh before it. No new migration/table in this
# track, so `docker compose up --build` is sufficient.
#
# What this script CANNOT verify (disclosed up front):
#   - The frontend's real rendered appearance (Open Conversations showing
#     a real number instead of "Not yet implemented", the breathing glow
#     firing when count > 0) - `tsc -b --force` confirms the frontend
#     compiles; a live browser check is still needed for the visual
#     result, same standing limitation as every prior frontend-touching
#     verify script in this project.
#   - No live AI provider call anywhere in this track - Open Conversations
#     is a plain COUNT(*) query, no AI involved at all.
set -euo pipefail

echo "=== 1/4: rebuild + boot ==="
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
echo "=== 2/4: route ordering sanity check (count must resolve BEFORE {conversation_id}) ==="
echo "-- a request to .../conversations/count must never be swallowed by the {conversation_id}: uuid.UUID route --"
docker compose exec -T backend python -c "
from app.main import app
paths = [r.path for r in app.routes if hasattr(r, 'path') and 'conversations' in r.path]
count_idx = next(i for i, p in enumerate(paths) if p.endswith('/conversations/count'))
detail_idx = next(i for i, p in enumerate(paths) if p.endswith('/conversations/{conversation_id}'))
assert count_idx < detail_idx, f'count route (index {count_idx}) must be registered before the {{conversation_id}} route (index {detail_idx})'
print('confirmed: /conversations/count is registered before /conversations/{conversation_id}')
"

echo
echo "=== 3/4: Track C1 test suite (real DB - tenant isolation, status filtering, zero-conversations edge case) ==="
docker compose exec -T backend python -m unittest tests.test_open_conversations_count -v

echo
echo "=== 4/4: manual checklist (no automated coverage exists for these) ==="
echo "-- in the browser, confirm the Open Conversations KPI card shows a real number, not 'Not yet implemented' --"
echo "-- with at least one open Conversation for the active business, confirm the card's glow is breathing (active), not just ambient --"
echo "-- with zero open conversations, confirm the card shows 0 and the glow is ambient-only (not breathing) --"

echo
echo "ALL CHECKS COMPLETE"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - Visual confirmation of the KPI card's real value and breathing-glow behavior requires a live browser - see"
echo "    this script's own header."
echo "  - Revenue Pipeline remains an honest placeholder - out of scope for Track C1, pending Track C3/C4."
