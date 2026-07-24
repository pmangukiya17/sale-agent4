#!/usr/bin/env bash
# M2 Phase 2 - External Research Provider Framework.
#
# CEO-directed scope (implementation approved directly, in the same
# message as the detailed spec - no separate architecture-proposal gate
# this sub-phase, mirroring Phase 1c's own precedent): transform
# Discovery into a provider-driven architecture while preserving the
# existing pipeline, per the CEO's full spec (goals, architecture
# requirements, provider interface, provider registry, first provider
# [Brave Search], normalization, multi-provider execution, failure
# handling, configuration, testing, regression, verification
# requirements) - which itself directly matches the ALREADY-APPROVED
# docs/architecture/m2-discovery-provider-strategy.md Section 11
# refinements (Search Service abstraction + Query Planner) this project
# had on file before this phase began.
#
# What this sub-phase built (all additive - no unrelated module
# refactored, no existing test weakened):
#   1. app/discovery/query_planner.py (NEW) - pure, zero-ORM-dependency
#      Query Planner: QueryPlanInput/QueryVariation/QueryPlan +
#      build_query_plan(), generating an explicit, explainable, bounded
#      (MAX_VARIATIONS_PER_PLAN=50) list of query variations from
#      Products/Buyer Types/Industries/Countries/Languages/Synonyms -
#      per architecture doc Section 11.2.
#   2. app/discovery/search_service.py (NEW) - the Search Service
#      abstraction (Section 11.1): SearchService.discover(provider_key,
#      query_plan, context) sits between app.discovery.pipeline and
#      every query-driven provider. Per-variation graceful degradation
#      (one variation failing doesn't fail the whole provider call -
#      only every variation failing raises ProviderError, which
#      pipeline.py's existing per-provider try/except already handles
#      exactly like any other provider failure). provider_lookup
#      constructor seam mirrors app.ai_gateway.client.AIGateway's own
#      precedent, keeping this module importable/testable without httpx.
#   3. app/discovery/providers/brave_search.py (NEW) - BraveSearchProvider,
#      the first query-driven provider (CEO-approved: "Brave Search API,
#      not because it's the default, but because it's the last one
#      standing" after Bing's retirement and Google Custom Search's
#      shutdown clock). httpx-based, its own internal timeout+retry
#      policy (settings.BRAVE_SEARCH_TIMEOUT_SECONDS/
#      BRAVE_SEARCH_MAX_RETRIES), health()/capabilities() overrides,
#      raises the new retryable ProviderError hierarchy
#      (ProviderTimeoutError/ProviderRateLimitError/ProviderAuthError/
#      ProviderUnavailableError - added to
#      app/discovery/providers/base.py, mirroring
#      app.ai_gateway.errors.GatewayError's own `retryable` flag
#      convention). UNVERIFIED BY EXECUTION against the real Brave API -
#      see this script's own disclosed-gaps section.
#   4. app/discovery/providers/brave_search_mapping.py (NEW) - the
#      "Candidate Extraction" step, deliberately split into its OWN
#      stdlib-only module (turns Brave's page-shaped web results into
#      company-shaped RawProviderResult candidates) so this logic is
#      genuinely unit-testable without httpx - see
#      tests/test_brave_search_mapping_pure.py.
#   5. app/discovery/providers/base.py - added health()/capabilities()/
#      provider_name() as new, non-abstract DiscoveryProvider methods
#      with safe defaults (ManualCSVProvider needed zero changes); added
#      the retryable ProviderError hierarchy; moved its DiscoveryContext
#      import behind TYPE_CHECKING (+ `from __future__ import
#      annotations`) so this module - and therefore search_service.py -
#      stays importable with zero sqlalchemy dependency, mirroring
#      app/discovery/dedup.py's/scoring.py's own established precedent.
#   6. app/discovery/providers/registry.py - rewritten to lazily import
#      each provider class inside get_provider() (mirroring
#      app.ai_gateway.client.AIGateway._resolve_provider()'s own
#      precedent exactly), so merely importing this module (and
#      therefore app.discovery.pipeline) never requires httpx to be
#      installed. Added SEARCH_PROVIDER_KEYS/DIRECT_PROVIDER_KEYS (the
#      manual_csv-stays-direct carve-out from architecture doc Section
#      11.1) and iter_enabled_providers() (the Provider Registry's own
#      "iterate active providers" requirement, backed by each provider's
#      own health()).
#   7. app/discovery/pipeline.py - one additive branch inside the
#      existing per-provider loop: for a search-type provider_key, build
#      a QueryPlan (via a new _build_query_plan_input() helper that
#      reads context.products/context.icp's own ORM relationships - the
#      same "touch the ORM here, hand primitives to the pure function"
#      split _load_known_industries() already established) and call
#      search_service.discover() instead of provider.search() directly.
#      Every cancellation checkpoint, every commit, every downstream
#      normalization/validation/dedup/scoring line is byte-for-byte
#      unchanged - both paths still produce the same ProviderSearchOutcome
#      shape this function already knew how to process.
#   8. app/core/config.py - BRAVE_SEARCH_API_KEY (no default, same
#      lazy-checked-at-first-use precedent as CREDENTIAL_ENCRYPTION_KEY/
#      ANTHROPIC_API_KEY)/BRAVE_SEARCH_ENABLED (explicit kill switch,
#      separate from "is a key configured")/BRAVE_SEARCH_BASE_URL/
#      BRAVE_SEARCH_TIMEOUT_SECONDS/BRAVE_SEARCH_MAX_RETRIES.
#   9. Five new test files, four genuinely EXECUTED in this sandbox
#      (41 tests, 2 environment-only skips - see disclosed gaps below),
#      one DB-backed and disclosed unrunnable here:
#      tests/test_query_planner_pure.py,
#      tests/test_brave_search_mapping_pure.py,
#      tests/test_search_service_pure.py (covers every CEO-listed
#      category: provider registry/lookup, provider interface, successful
#      execution, timeout, exception, multiple providers, duplicate
#      results across providers, provider disabled, graceful degradation),
#      tests/test_provider_registry_pure.py,
#      tests/test_discovery_search_service_e2e.py (DB-backed).
#
# No schema change, no new Alembic migration this phase - Brave Search
# configuration lives in environment variables (app.core.config), not
# the database, matching this codebase's own established convention for
# every other external-provider credential (GMAIL_OAUTH_CLIENT_ID,
# ANTHROPIC_API_KEY, etc.). alembic upgrade head below is still run as a
# regression guard (confirms Phase 1c's migration 0028 is still the
# clean head, unaffected by this phase).
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
echo "=== 2/7: migration regression guard - confirm head is still 0028 (no schema change this phase) ==="
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current
echo "-- expected: 0028 (head), no errors --"

echo
echo "=== 3/7: Phase 2's own new test suites (pure, DB-free - run for real here too, not just in this sandbox) ==="
docker compose exec -T backend python -m unittest \
  tests.test_query_planner_pure \
  tests.test_brave_search_mapping_pure \
  tests.test_search_service_pure \
  tests.test_provider_registry_pure \
  -v

echo
echo "=== 4/7: Phase 2's own new DB-backed test suite ==="
docker compose exec -T backend python -m unittest \
  tests.test_discovery_search_service_e2e \
  -v

echo
echo "=== 5/7: existing pure-logic suites - regression guard (Phase 1a/1b, re-run for real here) ==="
docker compose exec -T backend python -m unittest \
  tests.test_discovery_dedup_pure \
  tests.test_discovery_normalization \
  tests.test_discovery_validation \
  tests.test_discovery_scoring_pure \
  tests.test_opportunity_state_machine \
  tests.test_scope_utils \
  -v

echo
echo "=== 6/7: Discovery + Phase 1c regression - confirm the Search Service wiring didn't break the existing async workflow, cancellation, or Prospect Import ==="
docker compose exec -T backend python -m unittest \
  tests.test_discovery_workflow_e2e \
  tests.test_discovery_job_cancellation \
  tests.test_opportunities_e2e \
  -v

echo
echo "=== 7/7: full smoke test (must pass end-to-end with no regressions per the CEO's stated completion criteria) ==="
docker compose exec -T backend python smoke_test.py || python3 smoke_test.py

echo
echo "ALL AUTOMATED CHECKS COMPLETE"
echo
echo "Manual/inspection checklist:"
echo "-- (a) Set BRAVE_SEARCH_API_KEY in .env to a real Brave Search API"
echo "--     subscription key, restart the backend, then run a Discovery"
echo "--     search with provider_keys=[\"brave_search\"] against a real ICP"
echo "--     with at least one active Product - confirm real candidates come"
echo "--     back, DiscoveryJobProviderRun records a real request_count, and"
echo "--     job.status reaches completed --"
echo "-- (b) With BRAVE_SEARCH_API_KEY unset (the default, out of the box),"
echo "--     run a search with provider_keys=[\"manual_csv\", \"brave_search\"]"
echo "--     - confirm the job still completes (status=partially_completed),"
echo "--     manual_csv's own candidates are still created, and"
echo "--     job.error_message mentions brave_search being unconfigured -"
echo "--     this is exactly what tests/test_discovery_search_service_e2e.py's"
echo "--     TestUnconfiguredBraveSearchDegradesGracefully class asserts, but"
echo "--     against the REAL BraveSearchProvider (httpx installed in this"
echo "--     Docker image), not a sandbox-only skip --"
echo "-- (c) Temporarily set BRAVE_SEARCH_ENABLED=false with a real"
echo "--     BRAVE_SEARCH_API_KEY present - confirm brave_search is still"
echo "--     treated as unavailable (the explicit kill switch works"
echo "--     independently of whether a key is configured) --"
echo "-- (d) Point BRAVE_SEARCH_BASE_URL at an unreachable host temporarily -"
echo "--     confirm a Discovery job with brave_search enabled still"
echo "--     completes (partially_completed), never hangs past"
echo "--     BRAVE_SEARCH_TIMEOUT_SECONDS x (1 + BRAVE_SEARCH_MAX_RETRIES) per"
echo "--     query variation, and the job log shows the timeout being"
echo "--     retried the configured number of times before giving up --"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - This sandbox has neither Docker, Postgres, nor any PyPI/network"
echo "    access at all (confirmed again this phase: 'pip install httpx' has"
echo "    no path here either), so BraveSearchProvider.search()'s own real"
echo "    httpx call - the ONLY part of this phase's code that actually talks"
echo "    to a network - has never been executed, only manually cross-"
echo "    referenced against Brave's own published Web Search API docs (see"
echo "    that file's own UNVERIFIED BY EXECUTION docstring). Everything"
echo "    downstream of a raw Brave JSON response (candidate extraction,"
echo "    query planning, Search Service orchestration, retry/timeout"
echo "    control flow's SHAPE if not its real network timing, provider"
echo "    registry classification) WAS genuinely executed in this sandbox -"
echo "    41 tests, 2 skips (both skips are get_provider() actually"
echo "    instantiating a real provider class, which needs sqlalchemy/httpx"
echo "    respectively - neither installed here; the KeyError-for-unknown-key"
echo "    path, which needs neither, IS tested for real)."
echo "  - tests/test_discovery_search_service_e2e.py is DB-backed (real"
echo "    SessionLocal/Postgres) - not runnable in this sandbox, same"
echo "    disclosed limitation as every *_e2e.py test in this project."
echo "    Manual/inspection items (a)-(d) above are what actually close this"
echo "    gap; item (b) specifically re-runs that file's own"
echo "    TestUnconfiguredBraveSearchDegradesGracefully scenario against the"
echo "    real provider class rather than a patched one."
echo "  - No real Brave Search API subscription has ever been used against"
echo "    this code - BRAVE_SEARCH_API_KEY has no default (by design, same"
echo "    as every other external credential in this codebase) and this"
echo "    phase's own author has no such key to test with. Item (a) above is"
echo "    the CEO's own first real-world validation of this provider."
echo "  - True parallel multi-provider execution (Query Planner variations"
echo "    executed concurrently, or multiple providers executed"
echo "    concurrently) is explicitly NOT this phase's scope - both the"
echo "    CEO's own spec (\"sequential OK initially, future parallel must be"
echo "    possible without redesign\") and the pre-existing, approved"
echo "    architecture doc's phase table place real parallel execution in"
echo "    Phase 3, alongside OpenCorporates as the second provider. Nothing"
echo "    in this phase's design (SearchService.discover() being called once"
echo "    per provider_key from pipeline.py's existing outer loop) blocks"
echo "    that - a future Phase 3 change to how that outer loop is driven"
echo "    (e.g. a thread/async pool across provider_keys) would not need to"
echo "    change SearchService's own per-provider contract."
echo "  - Query Planner's own fan-out strategy is deliberately simple"
echo "    (products x countries, with buyer_type/industry/language/synonym"
echo "    as enrichment rather than additional cartesian dimensions) and"
echo "    capped at 50 variations - real fan-out tuning at production volume"
echo "    is explicitly named as Phase 4 \"scale hardening\" scope in the"
echo "    pre-existing architecture doc, not attempted here."
echo "  - No frontend UI changes this sub-phase (no way yet to add"
echo "    'brave_search' to a DiscoverySearch's provider_keys from the UI,"
echo "    no admin view of BRAVE_SEARCH_ENABLED/health()/"
echo "    iter_enabled_providers()) - the API/config surface exists, not yet"
echo "    a button. Same 'backend-only this sub-phase' scope decision"
echo "    Phase 1a/1b/1c already made for their own new surfaces."
