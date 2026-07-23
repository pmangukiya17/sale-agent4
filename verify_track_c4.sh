#!/usr/bin/env bash
# Track C4 (dashboard-capabilities-architecture-plan.md, Sections 2-4):
# Sales Pipeline, Pipeline Overview, and Revenue Pipeline - all three
# built entirely on the Opportunity domain Track C3 shipped. No new
# persistence or duplicate pipeline tables: Opportunity remains the
# single source of truth, OpportunityStageHistory remains the audit
# source of truth. This track only revises the two Track C3 service
# functions that back these widgets (compute_funnel gains conversion-
# rate math, compute_pipeline_value switches to a per-currency
# breakdown - see app/opportunities/service.py's own docstrings) and
# wires three frontend widgets to them.
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_*.sh before it. No new migration in this track -
# `docker compose up --build` is sufficient (migration 0025 from Track
# C3 already applies everything these widgets read).
#
# What this script CANNOT verify (disclosed up front):
#   - The frontend's real rendered appearance (Sales Pipeline's stage
#     boxes, Pipeline Overview's conversion percentages, Revenue
#     Pipeline's KPI number, and all three cards' breathing glow on real
#     Opportunity activity) - `tsc -b --force` confirms the frontend
#     compiles; a live browser check is still needed for the visual
#     result, same standing limitation as every prior frontend-touching
#     verify script in this project.
#   - No live AI provider call anywhere in this track - both endpoints
#     are plain aggregate queries over Opportunity, same as Track C3.
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
echo "=== 2/4: confirm Track C3's migration 0025 is still the current head (no new migration in this track) ==="
docker compose exec -T backend alembic current

echo
echo "=== 3/4: Track C3 real-DB suite still passes after the compute_funnel/compute_pipeline_value revisions ==="
docker compose exec -T backend python -m unittest tests.test_opportunity_state_machine tests.test_opportunities_e2e -v

echo
echo "=== 4/4: Track C4 metrics test suite (funnel conversion rates, per-currency revenue breakdown, empty pipeline, tenant isolation, edge cases) ==="
docker compose exec -T backend python -m unittest tests.test_pipeline_dashboard_metrics -v

echo
echo "ALL CHECKS COMPLETE"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - Visual confirmation of Sales Pipeline/Pipeline Overview/Revenue Pipeline's real rendered values and"
echo "    breathing-glow behavior requires a live browser - see this script's own header."
echo "  - Mailbox Brief (Track C5) remains an honest placeholder - out of scope for Track C4."
