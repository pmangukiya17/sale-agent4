#!/usr/bin/env bash
# M2 Phase 2 UX follow-up - Provider Visibility + Honest Controls.
#
# CEO-directed scope, per docs/architecture/m2-phase2-ux-provider-visibility-review.md
# and docs/architecture/m2-phase2-ux-implementation-plan.md (both approved,
# with one architectural refinement: API -> DiscoveryProviderService ->
# registry.py, rather than the API depending on registry.py directly).
#
# Priority 1 - Search Frequency: Daily/Weekly are now disabled <option>
#   elements (frontend/src/pages/DiscoverySearches.tsx) - visible, not
#   selectable, explanation text built into the option label itself.
# Priority 2 - Provider Visibility:
#   - New: app/discovery/provider_service.py (DiscoveryProviderService,
#     thin delegation to registry.py's new list_registered_provider_keys()).
#   - New: app/schemas/discovery_provider.py (DiscoveryProviderRead).
#   - New: app/api/routes/discovery_providers.py (GET /discovery-providers,
#     NOT company-profile-scoped - mirrors reference_data.py's own shape).
#   - New route registered in app/main.py.
#   - One-line addition: ManualCSVProvider.provider_name() override
#     ("Manual / CSV Import") for display-name parity with brave_search.
#   - Frontend: DiscoverySearches.tsx now fetches providers dynamically
#     (brave_search finally visible), shows a health Badge per provider,
#     and a static "Coming soon" list (OpenCorporates/Europages/TradeIndia/
#     Alibaba/Kompass) for unbuilt roadmap providers.
#   - Frontend: Prospects.tsx and DiscoveryJobs.tsx both now render one
#     Badge per provider (distinct provider_key on a Prospect's sources;
#     one per DiscoveryJobProviderRun on a job, colored by that run's own
#     status) - both against data the API already returned before this
#     phase, never a backend change for either.
#   - Shared: providerLabel() exported from useDiscoveryExecution.ts so
#     Prospects.tsx/DiscoveryJobs.tsx don't each maintain a second copy of
#     the "unrecognized provider_key still renders sensibly" fallback.
# Priority 3 - Search Depth: an informational caption under the Select,
#   not a disabled control (picking any value is harmless today, unlike
#   Search Frequency's "Daily" - see the implementation plan's own
#   reasoning for the different treatment).
# Priority 4 - Automation: untouched. No scheduler, no recurring-job
#   logic, nothing new in app.discovery.pipeline/search_service/
#   query_planner.
#
# Production backend code touched (exactly three items, all named for
# approval in the implementation plan): registry.py's new
# list_registered_provider_keys() accessor, ManualCSVProvider's new
# provider_name() override, and the one new route+schema+service.
# Nothing about how a provider is RESOLVED or EXECUTED during a real
# Discovery job changed - app.discovery.pipeline/search_service/
# query_planner are byte-for-byte unchanged this pass.
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
echo "=== 2/6: migration regression guard - no schema change this phase, head must still be 0028 ==="
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current

echo
echo "=== 3/6: this phase's own new test suites ==="
docker compose exec -T backend python -m unittest \
  tests.test_discovery_provider_service_pure \
  tests.test_discovery_providers_route \
  -v

echo
echo "=== 4/6: full Phase 2 + Phase 1 regression sweep (unrelated behavior must be unchanged) ==="
docker compose exec -T backend python -m unittest \
  tests.test_query_planner_pure \
  tests.test_brave_search_mapping_pure \
  tests.test_search_service_pure \
  tests.test_provider_registry_pure \
  tests.test_discovery_search_service_e2e \
  tests.test_discovery_dedup_pure \
  tests.test_discovery_normalization \
  tests.test_discovery_validation \
  tests.test_discovery_scoring_pure \
  tests.test_opportunity_state_machine \
  tests.test_scope_utils \
  tests.test_discovery_workflow_e2e \
  tests.test_discovery_job_cancellation \
  tests.test_opportunities_e2e \
  -v

echo
echo "=== 5/6: frontend build check (tsc -b) - real, executed here (this sandbox has node_modules and a working tsc, unlike the backend's own sqlalchemy/httpx situation) ==="
docker compose exec -T frontend npx tsc -b --force || (cd frontend && npx tsc -b --force)

echo
echo "=== 6/6: full smoke test (must pass end-to-end with no regressions) ==="
docker compose exec -T backend python smoke_test.py || python3 smoke_test.py

echo
echo "ALL AUTOMATED CHECKS COMPLETE"
echo
echo "Manual/inspection checklist:"
echo "-- (a) Open the Discovery Searches page's 'New search' form - confirm"
echo "--     'Brave Search' now appears in the Providers list (previously"
echo "--     invisible), with a 'Not configured' badge if BRAVE_SEARCH_API_KEY"
echo "--     is unset, or 'Ready' if it's set - and confirm its checkbox is"
echo "--     disabled while 'Not configured'."
echo "-- (b) Confirm OpenCorporates/Europages/TradeIndia/Alibaba/Kompass all"
echo "--     appear as disabled checkboxes with a 'Coming soon' badge,"
echo "--     visually distinct from a real-but-unconfigured provider."
echo "-- (c) Confirm the Search Frequency dropdown still shows Daily/Weekly"
echo "--     but they cannot be selected (grayed out), with the explanation"
echo "--     text visible in the option itself."
echo "-- (d) Confirm the Search Depth field now shows a small caption"
echo "--     ('Not yet used to vary search scope...') and all three values"
echo "--     remain freely selectable."
echo "-- (e) Run a search with provider_keys including brave_search (with a"
echo "--     real API key configured) or manual_csv, then open Prospects -"
echo "--     confirm each prospect shows a provider Badge matching who found"
echo "--     it; for a prospect re-sighted by two providers in one job,"
echo "--     confirm BOTH badges appear on the same row."
echo "-- (f) Open Discovery Jobs - confirm each job card's header now shows"
echo "--     one Badge per provider that ran, colored by that provider's own"
echo "--     run status (green=completed, red=failed, gray=cancelled),"
echo "--     alongside the existing detailed per-provider text below."
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - This sandbox has neither Docker, Postgres, nor sqlalchemy/httpx"
echo "    installed, so tests.test_discovery_providers_route.py (needs a"
echo "    real User model import) was only py_compile-checked, not executed,"
echo "    in the authoring sandbox - tests.test_discovery_provider_service_pure.py"
echo "    (zero third-party dependency) WAS genuinely executed there (6/6"
echo "    pass) and is what actually proves DiscoveryProviderService's own"
echo "    'never raises, degrades unhealthy providers gracefully' contract."
echo "  - tsc -b WAS genuinely run in the authoring sandbox (node_modules"
echo "    already present there) and passed clean, zero errors - this is"
echo "    the one piece of this phase's own verification that did NOT need"
echo "    Docker to prove for real."
echo "  - No automated frontend test suite exists in this project to extend"
echo "    (this project's automated test coverage is backend-only, per"
echo "    every prior milestone) - the manual checklist above (a)-(f) is"
echo "    this phase's own frontend correctness proof, same as every prior"
echo "    frontend-touching milestone in this project."
echo "  - GET /discovery-providers has never been called against a real,"
echo "    running server (no Docker access in the authoring sandbox) -"
echo "    step 1-4 above are this phase's first real-server proof."
