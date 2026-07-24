#!/usr/bin/env bash
# M2 Phase 1a - Discovery Normalization + Validation pipeline stages.
#
# CEO-approved as part of the M2 Discovery Provider Strategy (Search
# Service + Query Planner refinements) and the consolidated phase order:
# Phase 1 (this sub-phase, 1a) -> Phase 2 (Search abstraction + Brave
# Search) -> Phase 3 (OpenCorporates + multi-provider execution) ->
# Phase 4 (scale hardening). See
# docs/architecture/m2-buyer-discovery-engine-architecture-review.md and
# docs/architecture/m2-discovery-provider-strategy.md for the full design.
#
# What this sub-phase built, and why it required no schema change:
#   1. app/discovery/normalization.py (NEW) - a real, consistent producer
#      for DiscoveryProviderResult.normalized_payload, a column that has
#      existed since M1 but was previously populated ad hoc with raw
#      fields copied straight through. Also starts populating
#      Prospect.industry_id (existed since M1, nothing ever set it) via
#      deterministic keyword matching against the Industry reference
#      table - no new column, no new table.
#   2. app/discovery/validation.py (NEW) - a separate pipeline stage
#      answering "is this candidate well-formed at all?", deliberately
#      distinct from app/discovery/dedup.py's "have we seen this company
#      before?" (duplicate-confidence is explicitly NOT a validation
#      check - see the module's own docstring for the CEO-directed
#      correction). Failed candidates are recorded (inside the existing
#      normalized_payload JSONB column, under a new "validation" key -
#      still no schema change) but never turned into a Prospect.
#   3. app/discovery/dedup.py - one small, behavior-neutral import fix
#      (Prospect moved behind TYPE_CHECKING) so its own pure functions,
#      and normalization.py's reuse of them, are importable and
#      unit-testable without a working sqlalchemy install - this is what
#      makes items 4-5 below possible at all in a sandbox with no
#      Postgres/Docker access.
#   4. app/discovery/pipeline.py - wired both new stages in between
#      candidate collection and deduplication, using normalized (not raw)
#      name/website/country/industry_id when creating or matching a
#      Prospect. No new DiscoveryJob column: a validation-failure count
#      is appended to the existing job.log JSONB list instead of a new
#      counter column.
#   5. Three new, genuinely-executable test modules
#      (tests/test_discovery_dedup_pure.py, tests/test_discovery_normalization.py,
#      tests/test_discovery_validation.py) - all pure logic, zero
#      sqlalchemy dependency, actually run in the authoring sandbox (see
#      below), the same "pure logic, actually executed" precedent
#      tests/test_scope_utils.py and tests/test_opportunity_state_machine.py
#      already set.
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_*.sh before it.
set -euo pipefail

echo "=== 1/6: rebuild + boot ==="
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
echo "=== 2/6: confirm migration head unchanged (0026 - this sub-phase adds no migration) ==="
docker compose exec -T backend alembic current

echo
echo "=== 3/6: new M2 Phase 1a pure-logic test suites ==="
echo "-- these three were ALSO actually run in the authoring sandbox (see step 6) --"
docker compose exec -T backend python -m unittest \
  tests.test_discovery_dedup_pure \
  tests.test_discovery_normalization \
  tests.test_discovery_validation \
  -v

echo
echo "=== 4/6: regression suites - confirm Normalization/Validation wiring didn't break the existing Discovery pipeline ==="
docker compose exec -T backend python -m unittest \
  tests.test_discovery_workflow_e2e \
  -v

echo
echo "=== 5/6: full backend regression sweep (unrelated domains, confirming no accidental blast radius) ==="
docker compose exec -T backend python -m unittest \
  tests.test_opportunity_state_machine \
  tests.test_opportunities_e2e \
  tests.test_pipeline_dashboard_metrics \
  tests.test_mailbox_brief_e2e \
  tests.test_scope_utils \
  -v

echo
echo "=== 6/6: manual/inspection checklist ==="
echo "-- (a) Run a real Discovery search via manual_csv with a company whose industry_raw"
echo "--     approximately matches a real Industry row (e.g. 'Textiles Wholesale' against a"
echo "--     seeded 'Textiles' industry) - confirm the resulting Prospect.industry_id is set"
echo "--     (previously always NULL - GET the prospect and check industry_id is non-null,"
echo "--     industry_match_method is 'exact' or 'keyword' inside the DiscoveryProviderResult"
echo "--     row's normalized_payload) --"
echo "-- (b) Submit a manual_csv row that fails validation on purpose (e.g. name='Home',"
echo "--     website='not a domain') - confirm NO Prospect is created from it, confirm the"
echo "--     DiscoveryJob still completes normally (other valid rows in the same job still"
echo "--     produce Prospects), confirm job.log contains a 'candidate_failed_validation'"
echo "--     entry with the real reasons and a 'validation_summary' entry with a non-zero count --"
echo "-- (c) Confirm DiscoveryProviderResult.normalized_payload for a normal, valid candidate"
echo "--     now contains a nested 'validation': {'passed': true, 'checks': [...]} block, not"
echo "--     just the raw fields copied through as before --"
echo "-- (d) Confirm Prospect.website for a candidate submitted as e.g."
echo "--     'HTTPS://WWW.Example.COM/' is stored as the cleaned 'example.com' - the canonical"
echo "--     normalized form, not the raw provider string --"

echo
echo "ALL AUTOMATED CHECKS COMPLETE"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - This sandbox has neither Docker nor a working 'sqlalchemy' import (confirmed:"
echo "    'ModuleNotFoundError: No module named sqlalchemy'), so only the three pure-logic"
echo "    suites in step 3 (test_discovery_dedup_pure, test_discovery_normalization,"
echo "    test_discovery_validation - 44 tests total) were actually executed while authoring"
echo "    this sub-phase. Every DB-backed suite above (test_discovery_workflow_e2e and the"
echo "    step 5 regression sweep) is py_compile-checked only until run here for real."
echo "  - Country validity (check_country_known) has NO known_countries list wired up in"
echo "    pipeline.py yet - the check function supports it, but this sub-phase deliberately"
echo "    did not invent a country allowlist that doesn't exist anywhere else in this"
echo "    codebase; the check currently always skips (passed=True) in production, same as"
echo "    it does in the unit tests. Wiring a real list is a small, separate follow-up, not"
echo "    blocking for this sub-phase."
echo "  - Website reachability (check_website_reachable) is deliberately unwired by default"
echo "    (see validation.py's own docstring) - no network-calling provider exists yet"
echo "    (Phase 1 still runs only ManualCSVProvider); wiring a real HTTP check is explicitly"
echo "    deferred to Phase 2, alongside the rate-limit/async infrastructure a real check"
echo "    needs at scale (see docs/architecture/m2-discovery-provider-strategy.md Section 9)."
echo "  - Phase 1b (dedup signal expansion - VAT/registration number - + configurable/"
echo "    industry-weighted scoring) and Phase 1c (Prospect Import action + job"
echo "    cancellation) are NOT part of this sub-phase and have not been started."
