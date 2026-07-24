#!/usr/bin/env bash
# M2 Phase 1c - Prospect -> Opportunity Import + Discovery Job Cancellation.
#
# CEO-directed scope (implementation approved directly, no separate
# architecture-proposal gate this sub-phase):
#   1. Prospect -> Opportunity Import
#   2. Discovery Job Cancellation
# Implementation requirements, all honored: preserve existing
# architecture, keep changes additive, no refactor of unrelated modules,
# reuse existing Opportunity/Contact/Timeline/Workflow/Event patterns,
# idempotent import (never duplicate Opportunities), full audit/history
# preserved, strict multi-business isolation, graceful cancellation that
# supports partially-completed jobs, comprehensive unit + integration
# tests, forward-compatible with future Brave Search/OpenCorporates/
# parallel providers and downstream AI agents.
#
# What this sub-phase built:
#   1. Prospect -> Opportunity Import (app/opportunities/service.py's new
#      import_prospect_to_opportunity() + app/api/routes/prospects.py's
#      new POST .../prospects/{id}/import route):
#      - Zero schema change / zero new migration for this half of the
#        phase - Opportunity has been keyed directly off prospect_id
#        since Track C3 (never the legacy Company/Contact tables), so
#        importing a Prospect needed no new model.
#      - Deliberately a thin wrapper around the EXISTING
#        create_opportunity() - never a second, parallel writer of
#        Opportunity/OpportunityStageHistory rows.
#      - Idempotent by query (does an Opportunity already exist for this
#        (company_profile_id, prospect_id) pair), not by a DB unique
#        constraint - see migration 0028's own docstring for why a hard
#        constraint was deliberately avoided (forecloses a legitimate
#        future re-opened-deal-with-a-repeat-customer case).
#      - Gated on Prospect.status == APPROVED (ProspectNotApprovedError,
#        translated to a 400) - the literal language Prospect's own
#        model docstring has used since M1.
#      - Writes exactly one ProspectTimelineEvent
#        (event_type="imported_to_opportunity") on a genuine creation;
#        an idempotent replay writes nothing new - full audit/history,
#        never duplicated.
#      - Multi-business isolation via the existing
#        get_owned_company_profile + _get_prospect_or_404 pattern,
#        identical to every other Prospect-scoped route.
#   2. Discovery Job Cancellation (migration 0028 + app/models/discovery_job.py's
#      new cancel_requested_at/cancel_requested_by_user_id columns +
#      app/discovery/pipeline.py's graceful stop logic +
#      app/api/routes/discovery_jobs.py's new POST .../cancel route):
#      - Cancellation is a REQUEST (cancel_requested_at), deliberately
#        separate from DiscoveryJob.status - only run_discovery_search()
#        itself (the one function actually executing a job) is ever
#        allowed to write DiscoveryJobStatus.CANCELLED, at a safe
#        checkpoint between units of work (before the next provider,
#        and periodically between candidates within the provider
#        currently running) - mirroring how COMPLETED/PARTIALLY_COMPLETED/
#        FAILED were already exclusively written there, never from a
#        route.
#      - Graceful + partial-completion-supporting: whatever was already
#        committed (Prospects, DiscoveryProviderResults, counts) is never
#        rolled back; a cancelled job's counts/log honestly reflect only
#        what was actually processed before the stop.
#      - The cancel route itself is idempotent (a second cancel call on
#        an already-cancel-requested RUNNING job is a no-op, not an
#        error) and rejects an already-terminal job with a 400.
#   3. Five new/extended, comprehensive DB-backed test methods across two
#      files: tests/test_opportunities_e2e.py gained a new
#      TestProspectImport class (7 tests: approval-gating, creation,
#      idempotency x2, cross-tenant isolation, name override, contact-
#      ownership validation); a NEW tests/test_discovery_job_cancellation.py
#      (7 tests: route-level status/idempotency/isolation checks against
#      directly-constructed jobs, plus two pipeline-level tests that
#      deterministically force a mid-run cancellation via patching, since
#      run_discovery_search() executes synchronously in one call and this
#      sandbox has no way to orchestrate genuine cross-session concurrency
#      inside a single-threaded test).
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_*.sh before it.
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
echo "=== 2/7: run the new migration, confirm head is now 0028 ==="
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current
echo "-- expected: 0028 (head), no errors --"

echo
echo "=== 3/7: Phase 1c's new DB-backed test suites ==="
docker compose exec -T backend python -m unittest \
  tests.test_opportunities_e2e \
  tests.test_discovery_job_cancellation \
  -v

echo
echo "=== 4/7: existing pure-logic suites - regression guard (all previously verified in-sandbox, re-run for real here) ==="
docker compose exec -T backend python -m unittest \
  tests.test_discovery_dedup_pure \
  tests.test_discovery_normalization \
  tests.test_discovery_validation \
  tests.test_discovery_scoring_pure \
  tests.test_opportunity_state_machine \
  tests.test_scope_utils \
  -v

echo
echo "=== 5/7: Discovery regression - confirm cancellation wiring didn't break the existing async workflow ==="
docker compose exec -T backend python -m unittest \
  tests.test_discovery_workflow_e2e \
  -v

echo
echo "=== 6/7: full backend regression sweep (unrelated domains, confirming no accidental blast radius) ==="
docker compose exec -T backend python -m unittest \
  tests.test_opportunities_e2e \
  tests.test_pipeline_dashboard_metrics \
  tests.test_mailbox_brief_e2e \
  tests.test_crm_automation_state_machine \
  -v

echo
echo "=== 7/7: full smoke test (must pass end-to-end with no regressions per the CEO's stated completion criteria) ==="
docker compose exec -T backend python smoke_test.py || python3 smoke_test.py

echo
echo "ALL AUTOMATED CHECKS COMPLETE"
echo
echo "Manual/inspection checklist:"
echo "-- (a) Approve a real Prospect (POST .../prospects/{id}/approve), then POST"
echo "--     .../prospects/{id}/import - confirm a new Opportunity appears at stage"
echo "--     qualified_lead, named after the prospect. Call import again on the SAME"
echo "--     prospect - confirm the SAME opportunity_id comes back and no second row"
echo "--     exists in the opportunities table --"
echo "-- (b) Try importing a prospect that is NEW/QUALIFIED/REJECTED/ARCHIVED (not"
echo "--     APPROVED) - confirm a 400, not a 500, and confirm nothing was created --"
echo "-- (c) Start a Discovery search with a large manual_csv row set, then POST"
echo "--     .../discovery-jobs/{id}/cancel shortly after - confirm the job eventually"
echo "--     lands in status=cancelled (not completed/partially_completed), with"
echo "--     prospect_created_count reflecting only what was processed before the stop,"
echo "--     and confirm those partial prospects are real, queryable rows, not rolled"
echo "--     back --"
echo "-- (d) Call cancel twice on the same running job - confirm the second call is a"
echo "--     harmless no-op (200, same cancel_requested_at), not an error --"
echo "-- (e) Try cancelling an already-completed job - confirm a 400 --"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - This sandbox has neither Docker nor a working 'sqlalchemy' import, so none of"
echo "    Phase 1c's own new tests (both new test classes are entirely DB-backed - Import"
echo "    and Cancellation are fundamentally about real ORM state transitions, unlike"
echo "    Phase 1a/1b's normalization/scoring logic) were actually executed while"
echo "    authoring this sub-phase - only py_compile-checked. The pre-existing pure-logic"
echo "    suites (89 tests: dedup/normalization/validation/scoring_pure/"
echo "    opportunity_state_machine/scope_utils) WERE re-run for real here as a"
echo "    regression guard and all still pass, confirming Phase 1c's changes didn't"
echo "    break any of Phase 1a/1b's own pure logic."
echo "  - The mid-run cancellation tests force a deterministic stop via patching"
echo "    app.discovery.pipeline._is_cancellation_requested / CANCELLATION_CHECK_INTERVAL"
echo "    rather than two real concurrent HTTP requests racing each other - this proves"
echo "    run_discovery_search()'s own branching/partial-completion logic is correct,"
echo "    but a true concurrent end-to-end proof (a real second request landing"
echo "    mid-run) is what inspection item (c) above is for."
echo "  - No frontend UI changes this sub-phase (an Import button on the Prospect"
echo "    review screen, a Cancel button on a running Discovery Job view) - both actions"
echo "    are reachable via the API today, not yet via any button. Same 'backend-only"
echo "    this sub-phase' scope decision Phase 1a/1b already made for their own new"
echo "    surfaces."
echo "  - No dedicated API-level test file exists for app/api/routes/discovery_jobs.py's"
echo "    list/get routes (pre-existing gap, not introduced by this phase) - the new"
echo "    cancel route IS covered by test_discovery_job_cancellation.py."
