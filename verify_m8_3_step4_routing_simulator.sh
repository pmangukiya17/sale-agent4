#!/usr/bin/env bash
# M8.3 - AI Gateway Management & Control, STEP 4 ONLY (Routing Simulator)
#
# Builds on Steps 1-3 (Provider Config, Provider Management UI, Model
# Role Management - approved, verified, committed separately). Step 4 is
# READ-ONLY end to end - it EXPLAINS a routing decision, it never
# executes one: no provider is ever actually called, no setting is ever
# actually changed. Per the CEO's explicit Step 4 requirements
# (2026-07-28): show the complete provider decision chain, explain why
# each provider was selected or skipped, show fallback order, display
# estimated cost where available, display capability filters that
# affected routing - all satisfied by reusing the EXISTING pure routing/
# capability/tier machinery, never a parallel routing implementation.
#
#   Backend:
#   - app/ai_gateway/routing_simulator.py (NEW) - pure module (no
#     settings/sqlalchemy import at module level, same discipline
#     router.py/capabilities.py/tiers.py already established).
#     `build_simulation()` reuses `router._build_decision()`'s output and
#     `capabilities.filter_capable()`/`resolve_capabilities()` directly -
#     every "impure" fact (real is_configured(), real prices, the real
#     premium-approval-gate setting) is supplied by the caller as a plain
#     value/callable (the "pure core, impure shell" split
#     local_model_policy.py's own resolve_local_model() already
#     established for Step 3). Shows the FULL candidate chain (local +
#     free + premium, in preference order) - every candidate gets a node
#     with a state/reason, including ones that would never actually be
#     attempted (skipped_not_reached) - unlike the pre-existing (M8.2)
#     GET /ai-gateway/routing "live preview" (unchanged by this step),
#     which stops annotating once one candidate is reached.
#   - app/ai_gateway/ui_query.py: simulate_routing() - the impure glue,
#     wiring real settings.AI_MODE/PROVIDER_CLIENT_REGISTRY/is_configured()/
#     default_model/price table into build_simulation(). Accepts a
#     hypothetical `ai_mode_override` and per-provider
#     `provider_enabled_overrides` (never persisted, never touches real
#     state) - the CEO's own "what would happen if..." requirement.
#   - app/schemas/ai_gateway.py: RoutingSimulationRequest/
#     RoutingSimulationNodeRead/RoutingSimulationRead.
#   - app/api/routes/ai_gateway.py: POST /ai-gateway/routing/simulate -
#     NOT admin-gated (same trust level as the pre-existing GET
#     /ai-gateway/routing and POST .../test-connection - read-only, no
#     credential exposure). 400s on an unrecognized ai_mode_override or an
#     unknown provider_key in provider_enabled_overrides.
#
#   Frontend:
#   - ai-gateway/types.ts: RoutingSimulation* types (a deliberately
#     richer, 5-state node shape than the pre-existing RoutingNode, which
#     only ever replays a past/live decision).
#   - ai-gateway/providers/GatewayDataProvider.ts (+ApiGatewayProvider.ts,
#     +MockGatewayProvider.ts): simulateRouting() added to the provider
#     abstraction.
#   - ai-gateway/hooks/useRoutingSimulator.ts (NEW): manually-triggered
#     action hook (same convention as useTestConnection - never runs on
#     mount).
#   - ai-gateway/components/RoutingSimulatorPanel.tsx (NEW): capability
#     select, hypothetical AI-mode select, per-provider "real/force
#     enabled/force disabled" override selects, Run button, and a full
#     results display (outcome banner, capability-filter panel, ordered
#     decision-chain list with role/tier/state badges, reason text, and
#     per-1k/estimated cost). No Save button anywhere on this panel.
#   - pages/ai-gateway/AIGatewayRouting.tsx: wires the panel in above the
#     pre-existing (M8.2) live-preview cards, which are unchanged.
#
# NOT implemented this step (see Section 11's remaining build order):
# Provider Capability Viewer changes, Gateway Diagnostics, Premium
# Approval pre-authorization UI. Capability -> role preference ordering
# and AI_MODE persistence remain out of scope for editing (AI_MODE here
# is a HYPOTHETICAL, non-persisted simulator input only, never a real
# settings write - see Section 12 decisions, unchanged by this step).
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
echo "=== 3/5: this step's own new test suite ==="
docker compose exec -T backend python -m unittest \
  tests.test_routing_simulator_pure \
  -v

echo
echo "=== 4/5: FULL regression sweep ==="
docker compose exec -T backend python -m unittest \
  tests.test_model_role_management_pure \
  tests.test_model_role_management_e2e \
  tests.test_local_model_policy_pure \
  tests.test_provider_config_pure \
  tests.test_provider_config_e2e \
  tests.test_ai_gateway_provider_management_pure \
  tests.test_provider_management_e2e \
  tests.test_ai_provider_hierarchy_pure \
  tests.test_ai_provider_hierarchy_e2e \
  tests.test_ai_gateway_capabilities_pure \
  tests.test_ai_gateway_ui_query_e2e \
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
echo "tests.test_routing_simulator_pure (11 assertions - build_simulation()'s own"
echo "full state machine: basic chain walk, primary-not-configured fallthrough,"
echo "premium gated-behind-approval vs. gate-disabled vs. not-configured, the"
echo "override DI seam in both directions [really-unconfigured simulated as"
echo "enabled, and really-configured simulated as disabled, with 'configured' vs"
echo "'overridden' independently asserted], and capability-mismatch exclusion with"
echo "its own reason text and capability_excluded reporting) - genuinely pure,"
echo "zero third-party imports, since routing_simulator.py never imports settings"
echo "or sqlalchemy at module level. Also re-ran the full pre-existing"
echo "tests.test_model_role_management_pure, tests.test_local_model_policy_pure,"
echo "tests.test_provider_config_pure, tests.test_ai_gateway_provider_management_pure,"
echo "tests.test_ai_provider_hierarchy_pure, and tests.test_ai_gateway_capabilities_pure"
echo "suites for regression (101 assertions total, all pass, confirming Step 4 added"
echo "a new pure module without touching any existing pure-testable behavior). "
echo "py_compile ran clean across the ENTIRE backend tree. \`npx tsc --noEmit\` ran"
echo "clean across the entire frontend tree (new types.ts/GatewayDataProvider.ts/"
echo "ApiGatewayProvider.ts/MockGatewayProvider.ts/useRoutingSimulator.ts/"
echo "RoutingSimulatorPanel.tsx/AIGatewayRouting.tsx changes). CORRECTION (fixed"
echo "post-first-submission): RoutingSimulatorPanel.tsx originally passed"
echo "kind=\"warning\" to StatusIndicator for the 'waiting on approval' outcome -"
echo "StatusKind has no 'warning' member (it's active/waiting/success/failed/"
echo "idle/paused - see StatusIndicator.tsx's own docstring for the fixed,"
echo "system-wide vocabulary this project deliberately never expands without a"
echo "real architectural reason). Fixed by mapping outcome=\"waiting\" to the"
echo "ALREADY-EXISTING kind=\"waiting\" (an exact 1:1 semantic match - was never a"
echo "gap in the design system, just a mistaken new-tone invention on this"
echo "component's part) - zero StatusIndicator/design-system changes needed."
echo "Re-verified via both \`npx tsc --noEmit\` and \`npx tsc -b --force\` (the exact"
echo "type-check step \`npm run build\` itself runs first) - both exit 0 clean."
echo
echo "NOT run in the authoring sandbox - needs Docker, run for real above:"
echo "every *_e2e.py suite in step 4 (needs settings/sqlalchemy -"
echo "ui_query.simulate_routing() itself has no dedicated e2e test file this pass,"
echo "since it's a thin wiring layer over build_simulation() [pure-tested above]"
echo "and router._build_decision()/capabilities.derive_required_capabilities()"
echo "[both already pure-tested pre-existing suites] - manual verification (e)"
echo "below is the disclosed way to confirm the wiring itself), and the actual"
echo "full \`npm run build\` bundling step (vite build, the second half of"
echo "\`npm run build\` after \`tsc -b\`) - this authoring sandbox's own"
echo "@rollup/rollup-linux-arm64-gnu optional-dependency is missing AND its npm"
echo "registry access is blocked (403 Forbidden on a direct install attempt), a"
echo "pre-existing environment limitation unrelated to any code in this step -"
echo "confirmed by directly attempting \`npm run build\` here: \`tsc -b\` (the"
echo "type-check half, where the CEO's flagged StatusKind error would have"
echo "surfaced) exits 0 clean, then \`vite build\` itself fails to even start with"
echo "a MODULE_NOT_FOUND on the native rollup binary. This is the SAME disclosed"
echo "limitation every prior milestone's own verify script already notes; \`npx"
echo "tsc -b --force\` was used here as the closest in-sandbox proxy for the"
echo "type-check portion specifically. The Docker verify run above (step 5) uses"
echo "a correctly-provisioned Linux image with unrestricted npm access and does"
echo "NOT hit this limitation - THAT run is what actually confirms \`npm run"
echo "build\` succeeds end to end, including the vite bundle step this sandbox"
echo "cannot execute."
echo
echo "Manual verification checklist (this is the only way to see the real UI/wiring):"
echo "-- (a) Open AI Gateway > Routing - confirm the new Routing Simulator panel"
echo "--     renders above the pre-existing live-preview cards, which are"
echo "--     unaffected."
echo "-- (b) Run a simulation for 'Prospect Research' with no overrides - confirm"
echo "--     the outcome/node states/reasons match what the pre-existing live"
echo "--     preview shows for the same capability under current live settings."
echo "-- (c) Set 'AI mode (hypothetical)' to 'Premium only' - confirm ONLY premium"
echo "--     candidates appear in the chain, local/free candidates are absent (not"
echo "--     merely skipped) - matching router._build_decision()'s own"
echo "--     premium_only branch."
echo "-- (d) Force-disable Groq via its provider override select, run again for a"
echo "--     capability where Groq would normally be reached - confirm Groq shows"
echo "--     'Not configured' with an 'overridden' badge, its 'configured' field"
echo "--     (visible via network tab) still reflects its REAL live state, and the"
echo "--     next candidate in the chain now shows 'Would call'."
echo "-- (e) Force-enable a provider with no real credentials configured - confirm"
echo "--     it becomes reachable in the simulation (state=would_call), then"
echo "--     confirm NOTHING about that provider's real Provider Management config"
echo "--     changed (reload its config page - unaffected)."
echo "-- (f) Submit an invalid ai_mode_override (curl, e.g. 'nonsense_mode') -"
echo "--     confirm 400, not a silent hybrid_recommended fallback."
echo "-- (g) Submit an unknown provider_key in provider_enabled_overrides (curl) -"
echo "--     confirm 400."
echo
echo "Deferred, disclosed rather than silently dropped - see"
echo "docs/architecture/m8-3-ai-gateway-control-center-plan.md Section 11 for the"
echo "full remaining build order:"
echo "  - Provider Capability Viewer changes, Gateway Diagnostics, Premium"
echo "    Approval pre-authorization UI - Steps 5-7."
echo "  - Capability -> role preference ordering stays code-level (CEO-affirmed,"
echo "    Step 3 approval) - unrelated to and unchanged by this step."
