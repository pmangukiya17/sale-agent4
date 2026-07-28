#!/usr/bin/env bash
# M8.3 - AI Gateway Management & Control, STEP 5 ONLY (Provider Capability
# Viewer)
#
# Builds on Steps 1-4 (Provider Config, Provider Management UI, Model Role
# Management, Routing Simulator - all approved, verified, committed
# separately). Step 5 is READ-ONLY end to end: it displays what the AI
# Gateway already knows about each provider's capabilities - it never adds
# a new capability declaration, never changes routing behavior, and never
# writes anything. Per the CEO's explicit Step 5 requirements
# (2026-07-28): preserve the existing architecture; build on the current
# routing and provider metadata; display provider capabilities in a clear
# comparison view; clearly distinguish provider-level capabilities from
# model-specific capabilities; indicate unsupported capabilities
# explicitly; keep capability data centralized so future providers inherit
# the same system.
#
#   Backend:
#   - app/ai_gateway/capabilities.py: NEW diff_capabilities(base, other) ->
#     list[str] pure function (plus a derived _CAPABILITY_FIELD_NAMES
#     tuple, sourced from dataclasses.fields(ProviderCapabilities) so a
#     future capability field is automatically covered with no second
#     edit) - diffs a provider's provider-level default against its
#     effective (possibly per-model-overridden) capabilities, field by
#     field, in declaration order. No change to resolve_capabilities()/
#     _CAPABILITY_OVERRIDES/satisfies()/filter_capable() - this step reuses
#     the EXISTING two-level (provider-level vs. per-model) capability
#     model verbatim, it does not invent a second one.
#   - app/schemas/ai_gateway.py: CapabilityValuesRead (the 6 booleans +
#     max_context_tokens/max_output_tokens) + ProviderCapabilityRead
#     (provider_key/label/tier/default_model/provider_level/effective/
#     has_model_override/overridden_fields).
#   - app/ai_gateway/ui_query.py: list_provider_capabilities() - the impure
#     glue. Iterates PROVIDER_CLIENT_REGISTRY generically (never branches
#     on a provider name - same discipline every other registry-iterating
#     function in this package already follows), resolves each provider's
#     real default_model, calls the EXISTING resolve_capabilities()/
#     diff_capabilities() against real provider-level ClassVars, never
#     invents or hardcodes a capability value.
#   - app/api/routes/ai_gateway.py: GET /ai-gateway/capabilities - NOT
#     admin-gated (same trust level as GET /ai-gateway/providers and GET
#     /ai-gateway/settings - a read of what the Gateway can do, not a
#     credential or a write).
#
#   Frontend:
#   - ai-gateway/types.ts: CapabilityValues / ProviderCapability (mirrors
#     the backend schemas field-for-field, camelCase).
#   - ai-gateway/providers/GatewayDataProvider.ts (+ApiGatewayProvider.ts,
#     +MockGatewayProvider.ts): listProviderCapabilities() added to the
#     provider abstraction. MockGatewayProvider's fixture is a fresh,
#     deliberately honest one (provider_level === effective,
#     hasModelOverride: false for every provider) rather than reusing the
#     old ProviderSummary.capabilities flat list, matching today's real
#     backend truth (zero registered _CAPABILITY_OVERRIDES entries
#     anywhere in the codebase).
#   - ai-gateway/hooks/useProviderCapabilities.ts (NEW): auto-fetch-on-mount
#     hook, same contract as useProviders.ts (plain read, no admin gate).
#   - ai-gateway/components/ProviderCapabilityViewer.tsx (NEW): replaces
#     the earlier CapabilityMatrix placeholder (M8.1, deleted this step as
#     dead code once nothing referenced it). Two clearly separated
#     sections: (1) "Provider-level capabilities" - a capability x provider
#     grid where every cell shows an icon AND an explicit
#     "Supported"/"Not supported" text label (never icon/color alone), plus
#     a small indicator dot + tooltip on any field flagged by
#     overridden_fields; (2) "Model-specific (currently configured model)"
#     - default model, max context/output tokens, and an explicit
#     "N fields overridden" badge or "Using provider defaults" label per
#     provider.
#   - pages/ai-gateway/AIGatewayHealth.tsx: wires the new hook/component in
#     place of the deleted CapabilityMatrix; the pre-existing Provider
#     Health card above it is unchanged.
#
# NOT implemented this step (see Section 11's remaining build order):
# Gateway Diagnostics, Premium Approval pre-authorization UI. Capability ->
# role preference ordering stays code-level (CEO-affirmed, Step 3
# approval) - unrelated to and unchanged by this step. No real per-model
# capability override exists in this codebase yet (register_capability_
# override() is called nowhere in application code) - the viewer is built
# to show one honestly the moment a real one is registered, not to
# fabricate a demo difference today.
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
echo "=== 2/5: no new migration this step - confirm 0031 (Step 3) is still current ==="
docker compose exec -T backend alembic current

echo
echo "=== 3/5: this step's own new/extended test suites ==="
docker compose exec -T backend python -m unittest \
  tests.test_ai_gateway_capabilities_pure \
  tests.test_ai_gateway_ui_query_e2e \
  -v

echo
echo "=== 4/5: FULL regression sweep ==="
docker compose exec -T backend python -m unittest \
  tests.test_routing_simulator_pure \
  tests.test_model_role_management_pure \
  tests.test_model_role_management_e2e \
  tests.test_local_model_policy_pure \
  tests.test_provider_config_pure \
  tests.test_provider_config_e2e \
  tests.test_ai_gateway_provider_management_pure \
  tests.test_provider_management_e2e \
  tests.test_ai_provider_hierarchy_pure \
  tests.test_ai_provider_hierarchy_e2e \
  tests.test_ai_execution_platform_e2e \
  tests.test_supervisor_e2e \
  tests.test_supervisor_invocation_action_e2e \
  tests.test_llm_mapping_pure \
  tests.test_research_analysis_agent_pure \
  tests.test_research_analysis_agent_full_chain_e2e \
  tests.test_llm_analysis_engine_e2e \
  tests.test_analysis_engine_registry_e2e \
  tests.test_research_workflow_e2e \
  -v

echo
echo "=== 5/5: frontend build ==="
docker compose exec -T frontend npx tsc -b --force || (cd frontend && npx tsc -b --force)
docker compose exec -T frontend npm run build || (cd frontend && npm run build)

echo
echo "ALL AUTOMATED CHECKS COMPLETE"
echo
echo "Genuinely executed in the authoring sandbox (no Docker/network access to"
echo "install sqlalchemy, pydantic, pydantic_settings, anthropic, openai, or"
echo "google-genai - confirmed by direct import attempts):"
echo "tests.test_ai_gateway_capabilities_pure - 30 assertions total (24 pre-existing"
echo "+ 6 new TestDiffCapabilities cases: identical inputs -> empty diff, two"
echo "all-conservative defaults -> empty diff [today's real state], a single-field"
echo "difference, multiple differences preserving ProviderCapabilities' own"
echo "dataclass field order, a real register_capability_override() ->"
echo "resolve_capabilities() -> diff_capabilities() round trip correctly detecting"
echo "the overridden fields, and a model with no registered override diffing to"
echo "empty) - genuinely pure, zero third-party imports, since capabilities.py"
echo "never imports settings or sqlalchemy at module level. Also re-ran the full"
echo "pre-existing tests.test_routing_simulator_pure, tests.test_model_role_"
echo "management_pure, tests.test_local_model_policy_pure, tests.test_provider_"
echo "config_pure, tests.test_ai_gateway_provider_management_pure, and tests.test_"
echo "ai_provider_hierarchy_pure suites for regression (107 assertions total across"
echo "all pure suites, all pass, confirming Step 5 added one new pure function"
echo "without touching any existing pure-testable behavior). py_compile ran clean"
echo "across the ENTIRE backend tree (app/ + tests/). \`npx tsc -b --force\` ran"
echo "clean (exit 0) across the entire frontend tree, including the new types.ts/"
echo "GatewayDataProvider.ts/ApiGatewayProvider.ts/MockGatewayProvider.ts/"
echo "useProviderCapabilities.ts/ProviderCapabilityViewer.tsx/AIGatewayHealth.tsx"
echo "changes and the CapabilityMatrix.tsx deletion (confirmed nothing else"
echo "referenced it before removing it)."
echo
echo "NOT run in the authoring sandbox - needs Docker, run for real above:"
echo "tests.test_ai_gateway_ui_query_e2e's new TestProviderCapabilities class (4"
echo "assertions: covers the full PROVIDER_CLIENT_REGISTRY, every entry has a valid"
echo "tier/non-empty label, no entry reports a model override today [honest"
echo "assertion of _CAPABILITY_OVERRIDES' current empty state - deliberately not a"
echo "vacuous pass, since it would fail loudly if a real override were later"
echo "registered without updating this test], and provider_level matches each"
echo "ProviderClient subclass's own .capabilities ClassVar directly) - needs"
echo "sqlalchemy/a real DB session, same reason importing app.ai_gateway.ui_query"
echo "needs Docker for every other test in that file. Also NOT run here: the"
echo "actual full \`npm run build\` bundling step (vite build, the second half of"
echo "\`npm run build\` after \`tsc -b\`) - this authoring sandbox's own"
echo "@rollup/rollup-linux-arm64-gnu optional-dependency is missing AND its npm"
echo "registry access is blocked (403 Forbidden on a direct install attempt), a"
echo "pre-existing environment limitation unrelated to any code in this step -"
echo "confirmed by directly attempting \`npm run build\` here: \`tsc -b\` (the"
echo "type-check half) exits 0 clean, then \`vite build\` itself fails to even start"
echo "with a MODULE_NOT_FOUND on the native rollup binary. This is the SAME"
echo "disclosed limitation every prior milestone's own verify script already"
echo "notes; \`npx tsc -b --force\` was used here as the closest in-sandbox proxy"
echo "for the type-check portion specifically. The Docker verify run above (step"
echo "5) uses a correctly-provisioned Linux image with unrestricted npm access and"
echo "does NOT hit this limitation - THAT run is what actually confirms \`npm run"
echo "build\` succeeds end to end, including the vite bundle step this sandbox"
echo "cannot execute."
echo
echo "Manual verification checklist (this is the only way to see the real UI/wiring):"
echo "-- (a) Open AI Gateway > Health - confirm the 'Provider Capabilities' card"
echo "--     renders in place of the old Capability Matrix, above the unaffected"
echo "--     'Failover events / routing statistics / diagnostics' PlaceholderNotice."
echo "-- (b) In the provider-level capability grid, confirm EVERY cell shows both"
echo "--     an icon AND a visible 'Supported'/'Not supported' text label (not"
echo "--     icon/color alone) - inspect a couple of 'Not supported' cells"
echo "--     specifically (e.g. streaming, which is false for every provider today"
echo "--     per capabilities.py's own disclosed AIGateway.stream() limitation)."
echo "-- (c) Confirm the model-specific table's default-model column shows 'Not"
echo "--     configured' (not a fabricated model name) for whichever provider(s)"
echo "--     currently have no default_model set, matching Provider Health's own"
echo "--     'not_configured' status for that same provider."
echo "-- (d) Confirm every provider's 'Overrides' column reads 'Using provider"
echo "--     defaults' - today's honest state, since no real per-model capability"
echo "--     override is registered anywhere in the codebase."
echo "-- (e) curl GET /api/v1/ai-gateway/capabilities directly - confirm the JSON"
echo "--     response covers exactly the 6 providers in PROVIDER_CLIENT_REGISTRY,"
echo "--     each with provider_level == effective and has_model_override: false."
echo "-- (f) Confirm a non-admin, signed-in user can load this page/endpoint (no"
echo "--     403) - this read is intentionally not admin-gated, same trust level as"
echo "--     GET /ai-gateway/providers."
echo
echo "Deferred, disclosed rather than silently dropped - see"
echo "docs/architecture/m8-3-ai-gateway-control-center-plan.md Section 11 for the"
echo "full remaining build order:"
echo "  - Gateway Diagnostics, Premium Approval pre-authorization UI - Steps 6-7."
echo "  - Capability -> role preference ordering stays code-level (CEO-affirmed,"
echo "    Step 3 approval) - unrelated to and unchanged by this step."
echo "  - A real per-model capability override (register_capability_override())"
echo "    has never been called from application code - this viewer is ready to"
echo "    show one honestly the moment that changes, but none exists today."
