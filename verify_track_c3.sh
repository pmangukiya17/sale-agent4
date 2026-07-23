#!/usr/bin/env bash
# Track C3 (dashboard-capabilities-architecture-plan.md, Section 1):
# Opportunity domain - the platform's first real, monetary sales-deal
# model. New migration 0025 (opportunities, opportunity_stage_history,
# two new enum types), new app/opportunities/ package
# (state_machine.py/service.py), new app/api/routes/opportunities.py (8
# endpoints), no frontend changes in this track (Sections 2-4's widgets
# are Track C4, on top of this foundation).
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_*.sh before it. This track DOES add a new
# migration (0025) - step 2 below runs `alembic upgrade head` explicitly
# (docker compose up --build alone does not guarantee a fresh container
# runs pending migrations if the entrypoint doesn't already do so; this
# script does not assume either way and runs it directly to be sure).
#
# What this script CANNOT verify (disclosed up front):
#   - No frontend/browser check in this track at all - Track C3 has zero
#     UI surface of its own; Sales Pipeline/Pipeline Overview/Revenue
#     Pipeline (Track C4) are what will actually render this data.
#   - No live AI provider call anywhere in this track - Opportunity is
#     deterministic data-entry + stage transitions, not a synthesis
#     domain (see app/opportunities/__init__.py's own docstring).
set -euo pipefail

echo "=== 1/5: rebuild + boot ==="
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
echo "=== 2/5: apply migration 0025 (opportunities, opportunity_stage_history) ==="
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current

echo
echo "=== 3/5: pure state-machine unit tests (no DB - stage skipping, no-op rejection, closed_at derivation) ==="
docker compose exec -T backend python -m unittest tests.test_opportunity_state_machine -v

echo
echo "=== 4/5: route ordering sanity check (funnel/pipeline-value must resolve BEFORE {opportunity_id}) ==="
echo "-- requests to .../opportunities/funnel and .../opportunities/pipeline-value must never be swallowed by the {opportunity_id}: uuid.UUID route --"
docker compose exec -T backend python -c "
from app.main import app
paths = [r.path for r in app.routes if hasattr(r, 'path') and 'opportunities' in r.path]
funnel_idx = next(i for i, p in enumerate(paths) if p.endswith('/opportunities/funnel'))
value_idx = next(i for i, p in enumerate(paths) if p.endswith('/opportunities/pipeline-value'))
detail_idx = next(i for i, p in enumerate(paths) if p.endswith('/opportunities/{opportunity_id}'))
assert funnel_idx < detail_idx, f'funnel route (index {funnel_idx}) must be registered before the {{opportunity_id}} route (index {detail_idx})'
assert value_idx < detail_idx, f'pipeline-value route (index {value_idx}) must be registered before the {{opportunity_id}} route (index {detail_idx})'
print('confirmed: /opportunities/funnel and /opportunities/pipeline-value are both registered before /opportunities/{opportunity_id}')
"

echo
echo "=== 5/5: Track C3 real-DB test suite (CRUD, stage transitions incl. skipping, tenant isolation, history tracking, edge cases) ==="
docker compose exec -T backend python -m unittest tests.test_opportunities_e2e -v

echo
echo "ALL CHECKS COMPLETE"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - No frontend/browser check in this track - see this script's own header. Sales Pipeline/Pipeline"
echo "    Overview/Revenue Pipeline (Track C4) are the widgets that will actually read this data."
echo "  - AI Recommendations/Mailbox Brief (Track C5) and any future AI-driven Opportunity suggestion remain"
echo "    out of scope for this track."
