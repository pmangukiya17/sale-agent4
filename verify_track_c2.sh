#!/usr/bin/env bash
# Track C2 (dashboard-capabilities-architecture-plan.md): AI
# Recommendations - a new cross-portfolio GET .../recommendations
# endpoint (app/api/routes/recommendations.py), backend tenant-isolation
# tests, and the frontend widget wired to it.
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_*.sh before it. No new migration/table in this
# track (the Recommendation model and its per-prospect routes already
# existed) - `docker compose up --build` is sufficient.
#
# What this script CANNOT verify (disclosed up front):
#   - The frontend's real rendered appearance (AI Recommendations showing
#     real recommendation rows instead of "Capability not yet
#     implemented", the breathing glow firing when recommendations exist)
#     - `tsc -b --force` confirms the frontend compiles; a live browser
#     check is still needed for the visual result, same standing
#     limitation as every prior frontend-touching verify script in this
#     project.
#   - No live AI provider call anywhere in this track - the cross-
#     portfolio endpoint only reads Recommendation rows the AI Analysis
#     Engine already wrote in an earlier milestone; it does not generate
#     new recommendations itself.
set -euo pipefail

echo "=== 1/3: rebuild + boot ==="
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
echo "=== 2/3: Track C2 test suite (real DB - portfolio tenant isolation, status filter, limit, empty-portfolio edge case) ==="
docker compose exec -T backend python -m unittest tests.test_ai_recommendations_portfolio -v

echo
echo "=== 3/3: manual checklist (no automated coverage exists for these) ==="
echo "-- in the browser, confirm the AI Recommendations card shows real recommendation rows, not 'Not yet implemented' --"
echo "-- with at least one recommendation for the active business, confirm the card's glow is breathing (active), not just ambient --"
echo "-- with zero recommendations, confirm the card shows the honest 'No recommendations yet' no-data notice and the glow is ambient-only (not breathing) --"

echo
echo "ALL CHECKS COMPLETE"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - Visual confirmation of the widget's real rows and breathing-glow behavior requires a live browser - see"
echo "    this script's own header."
echo "  - Revenue Pipeline and the remaining Track C3-C5 capabilities remain honest placeholders - out of scope for"
echo "    Track C2."
