#!/usr/bin/env bash
# M2 Phase 1b - Dedup signal expansion (government identifiers) +
# configurable, industry-weighted scoring.
#
# CEO-approved architecture (docs/architecture/
# m2-phase1b-dedup-scoring-architecture.md) with three required
# refinements, all implemented exactly as directed:
#   1. Scoring defaults: exact CEO-mandated split - Product Relevance 25,
#      Buyer Type 20, Industry 20, Market 20, Company Size 15 (sums to
#      100). Backend supports fully custom per-ICP weights immediately
#      (ICPCriteria.rules["scoring_weights"], the existing JSONB escape
#      hatch - no new column); no UI beyond the default preset yet.
#   2. Government identifiers: VAT number and Registration Number are two
#      separate, independently-indexed Prospect columns (not one combined
#      field), looked up via a generic, extensible IDENTIFIER_FIELDS list
#      in the new app/discovery/identifier_lookup.py - a future third/
#      fourth identifier type is a one-line addition, not a redesign.
#   3. Historical scoring: existing Prospect scores are NEVER
#      auto-recalculated when an ICP's weights change - score_prospect()
#      is only ever called from pipeline.py's per-run scoring pass. No
#      code path in this phase re-scores a prospect outside of a
#      discovery run that actually touched it.
#
# What this sub-phase built:
#   1. alembic/versions/0027_dedup_identifiers_industry_scoring.py (NEW) -
#      Prospect.vat_number/registration_number (indexed) + email
#      (unindexed, not a dedup signal) + icp_criteria_target_industries
#      junction table (same shape as the four existing ICPCriteria
#      junction tables).
#   2. app/discovery/identifier_lookup.py (NEW) - tier 1 of a now
#      three-tier dedup system (identifier exact match, checked before
#      dedup.py's existing website match / fuzzy name+country tiers).
#      Deliberately a SEPARATE module from dedup.py, not a new function
#      added to it, per the CEO's explicit direction - keeps dedup.py's
#      pure functions genuinely sqlalchemy-free.
#   3. app/discovery/normalization.py - normalize_vat_number()/
#      normalize_registration_number() + threaded vat_number/
#      registration_number/email through NormalizedCandidate.
#   4. app/discovery/validation.py - check_identifier_format(), a shallow
#      structural sanity check (not a per-country format validator - out
#      of scope) so an obviously-garbage identifier never reaches tier 1
#      of dedup at confidence 1.0.
#   5. app/discovery/scoring.py - rebalanced to the CEO-mandated defaults,
#      added the new industry_match factor, added resolve_weights() (the
#      configurable-weights merge logic) and made every _score_* function
#      accept its weight as a parameter instead of reading a module
#      constant directly. ICPCriteria/Product/Prospect imports moved
#      behind TYPE_CHECKING (mirroring dedup.py's Phase 1a change) so
#      this module's logic is now ALSO genuinely unit-testable without a
#      working sqlalchemy install - a new capability this sub-phase adds,
#      not just a refactor for its own sake.
#   6. app/models/{associations,icp_criteria,prospect}.py - the new
#      junction table + relationship + ICPCriteria.scoring_weights
#      read-only @property (derived from rules, never a mapped column) +
#      the three new Prospect columns.
#   7. app/discovery/providers/base.py + manual_csv.py - RawProviderResult
#      gained vat_number/registration_number/email; ManualCSVProvider
#      reads them from each row - makes the new dedup tier reachable
#      end-to-end via the real API, not just unit-testable in isolation.
#      (No frontend form fields added this sub-phase - same "backend-only
#      this sub-phase" scope decision Phase 1a made for its own new
#      fields; flagging for a follow-up if the CEO wants the manual-entry
#      UI to expose these too.)
#   8. app/discovery/pipeline.py - tier-1 identifier check now runs before
#      the existing find_duplicate() call; a new
#      _backfill_identifier_fields() helper opportunistically fills in a
#      missing vat_number/registration_number/email on ANY re-sighting
#      (identifier match, website match, or flagged duplicate) without
#      ever silently overwriting a conflicting existing value.
#   9. app/schemas/icp_criteria.py + app/api/routes/icp_criteria.py -
#      scoring_weights (validated: known factor names only, must sum to
#      100) and target_industry_ids/target_industries wired through,
#      following this file's existing _resolve_ids()/_apply_relations()
#      conventions exactly.
#  10. Five new/extended, genuinely-executable pure-logic test modules
#      (tests/test_discovery_scoring_pure.py is NEW; normalization/
#      validation/dedup suites extended in place) - same "pure logic,
#      actually executed in the authoring sandbox" precedent Phase 1a's
#      own verify script established. Two new DB-backed test methods were
#      also added to tests/test_discovery_workflow_e2e.py (tier-1 dedup +
#      identifier backfill) - py_compile-checked only until run here.
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
echo "=== 2/7: run the new migration, confirm head is now 0027 ==="
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current
echo "-- expected: 0027 (head), no errors --"

echo
echo "=== 3/7: new/extended M2 Phase 1b pure-logic test suites ==="
echo "-- all of these were ALSO actually run in the authoring sandbox (see step 7) --"
docker compose exec -T backend python -m unittest \
  tests.test_discovery_dedup_pure \
  tests.test_discovery_normalization \
  tests.test_discovery_validation \
  tests.test_discovery_scoring_pure \
  -v

echo
echo "=== 4/7: regression + new DB-backed Phase 1b coverage (tier-1 identifier dedup, backfill) ==="
docker compose exec -T backend python -m unittest \
  tests.test_discovery_workflow_e2e \
  -v

echo
echo "=== 5/7: full backend regression sweep (unrelated domains, confirming no accidental blast radius) ==="
docker compose exec -T backend python -m unittest \
  tests.test_opportunity_state_machine \
  tests.test_opportunities_e2e \
  tests.test_pipeline_dashboard_metrics \
  tests.test_mailbox_brief_e2e \
  tests.test_scope_utils \
  -v

echo
echo "=== 6/7: full smoke test (must pass end-to-end per the CEO's stated Phase 1b completion criteria) ==="
docker compose exec -T backend python smoke_test.py || python3 smoke_test.py

echo
echo "=== 7/7: manual/inspection checklist ==="
echo "-- (a) Create/update an ICPCriteria with scoring_weights e.g."
echo "--     {\"product_keyword_relevance\": 40, \"buyer_type_match\": 15, \"industry_match\": 15,"
echo "--      \"market_match\": 15, \"company_size_match\": 15} - confirm GET returns the same"
echo "--     scoring_weights back, and confirm ICPCriteria.rules in the DB now contains"
echo "--     {\"scoring_weights\": {...}} nested under the existing rules JSONB column (no new"
echo "--     column) --"
echo "-- (b) Try scoring_weights that DON'T sum to 100, or that include an unknown factor name"
echo "--     - confirm a 422 with a clear message, not a silent acceptance --"
echo "-- (c) Submit two manual_csv rows in the same Discovery search with the same vat_number"
echo "--     but clearly different names/no shared website - confirm only ONE Prospect is"
echo "--     created and the second row's ProspectTimelineEvent is reseen_by_provider with"
echo "--     matched_via=identifier (not website/fuzzy) --"
echo "-- (d) Run that same search again with a row carrying the same vat_number PLUS a new"
echo "--     registration_number the existing Prospect didn't have - confirm the existing"
echo "--     Prospect's registration_number gets backfilled, not left null --"
echo "-- (e) Set an ICP's target_industry_ids to a real Industry, run a search whose"
echo "--     industry_raw resolves to that Industry (Phase 1a's resolve_industry()) - confirm"
echo "--     the resulting Prospect's score_breakdown contains an industry_match entry with"
echo "--     matched=true and the configured (or default 20) weight's worth of points --"
echo "-- (f) Change an ICP's scoring_weights AFTER prospects already exist - confirm those"
echo "--     existing prospects' total_score/score_breakdown do NOT change (per the CEO's"
echo "--     explicit 'no auto-recalculation' refinement) - only prospects touched by a NEW"
echo "--     discovery run get scored with the new weights --"

echo
echo "ALL AUTOMATED CHECKS COMPLETE"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - This sandbox has neither Docker nor a working 'sqlalchemy' import (confirmed:"
echo "    'ModuleNotFoundError: No module named sqlalchemy'), so only the pure-logic suites in"
echo "    step 3 (71 tests total: 57 pre-existing + extended, plus 14 new in"
echo "    test_discovery_scoring_pure) were actually executed while authoring this sub-phase."
echo "    Every DB-backed suite above (test_discovery_workflow_e2e including its two new Phase"
echo "    1b test methods, the step 5 regression sweep, and the migration itself) is"
echo "    py_compile-checked only until run here for real."
echo "  - No dedicated API-level test file exists for app/api/routes/icp_criteria.py (there"
echo "    wasn't one before this phase either) - scoring_weights/target_industry_ids wiring"
echo "    through that route is covered by inspection item (a)/(b) above, not an automated"
echo "    test. A follow-up test_icp_criteria_routes.py would close this gap if desired."
echo "  - No frontend UI changes this sub-phase (manual_csv row entry, ICP scoring-weights"
echo "    editor) - same 'backend-only this sub-phase' scope decision Phase 1a made; the new"
echo "    fields are reachable via the API today, not yet via any form."
echo "  - Conflict handling for two DIFFERENT values on the same identifier field (e.g. two"
echo "    occurrences disagreeing on registration_number) is logged (as an"
echo "    identifier_conflicts entry on the reseen_by_provider timeline event) but never"
echo "    surfaced anywhere in the UI and never blocks/flags the prospect - a deliberately"
echo "    bounded interpretation, not a full conflict-resolution workflow (see"
echo "    docs/architecture/m2-phase1b-dedup-scoring-architecture.md's own risk section)."
echo "  - Phase 1c (Prospect Import action + job cancellation) is NOT part of this sub-phase"
echo "    and has not been started."
