#!/usr/bin/env bash
# M8.3 - AI Gateway Management & Control, STEP 2 ONLY (Provider Management)
#
# Builds on Step 1 (provider_config.py + ai_provider_configs/
# ai_provider_config_audits + encrypted credential storage + the
# ProviderClient refactor - approved, verified, committed separately, see
# verify_m8_3_step1_provider_config.sh). Step 2 is the first WRITE
# surface this codebase's AI Gateway UI has ever had:
#
#   Backend:
#   - app/ai_gateway/providers/base.py: ConnectionTestResult dataclass +
#     ProviderClient.test_connection() default (not-configured -> honest
#     failure, never raises; a configured-but-not-overridden fake client
#     raises NotImplementedError, matching default_model's own
#     backward-compat precedent).
#   - app/ai_gateway/providers/{claude,openai,gemini,openai_compatible}_client.py:
#     each real client's own test_connection() override - a cheap
#     models-list call (never a real completion), never bills real usage.
#   - app/schemas/ai_gateway.py: ProviderConfigWrite/ProviderConfigRead/
#     AIProviderConfigAuditRead/ConnectionTestResultRead.
#   - app/ai_gateway/ui_query.py: get_provider_config()/
#     list_provider_config_audit() - thin, read-only projections.
#   - app/api/routes/ai_gateway.py: PUT/GET /ai-gateway/providers/{key}/config
#     and GET .../config/audit (admin-gated - get_current_active_admin,
#     same precedent as POST /auth/register) + POST .../test-connection
#     (NOT admin-gated - never mutates anything, never exposes a
#     credential, same trust level as the existing read-only GET
#     /ai-gateway/providers/{key}).
#
#   Frontend:
#   - ai-gateway/types.ts: ProviderConfig/ProviderConfigWrite/
#     ProviderConfigAuditEntry/ConnectionTestResult.
#   - ai-gateway/providers/GatewayDataProvider.ts (+ApiGatewayProvider.ts,
#     +MockGatewayProvider.ts): getProviderConfig/saveProviderConfig/
#     listProviderConfigAudit/testConnection added to the provider
#     abstraction every hook already depends on.
#   - ai-gateway/hooks/useProviderConfig.ts (NEW): useProviderConfig,
#     useProviderConfigAudit, useTestConnection.
#   - ai-gateway/components/ProviderConfigPanel.tsx (NEW): the actual
#     Provider Management form - enable/disable, API key (write-only,
#     never echoed back), base URL, default model, Save, Test Connection
#     + result, and (admin-only) configuration history. Write controls
#     are gated client-side on useAuth().user.role === "admin" purely as
#     a UX courtesy - the backend independently enforces this regardless.
#   - pages/ai-gateway/AIGatewayProviderDetail.tsx: wires the panel in,
#     replacing the old "not yet implemented" configuration placeholder.
#
# NOT implemented this step (see Section 11's remaining build order):
# Model Role Management UI, Routing Simulator, Capability Viewer changes,
# Gateway Diagnostics, Premium Approval pre-authorization UI, per-provider
# retry/timeout override (CEO decision: stays global).
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
echo "=== 2/5: no new migration this step - confirm 0030 (Step 1) is still current ==="
docker compose exec -T backend alembic current

echo
echo "=== 3/5: this step's own new test suites ==="
docker compose exec -T backend python -m unittest \
  tests.test_ai_gateway_provider_management_pure \
  tests.test_provider_management_e2e \
  -v

echo
echo "=== 4/5: FULL regression sweep - every provider client file touched again (test_connection added), so this is deliberately as broad as Step 1's own sweep ==="
docker compose exec -T backend python -m unittest \
  tests.test_provider_config_pure \
  tests.test_provider_config_e2e \
  tests.test_local_model_policy_pure \
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
echo "google-genai - confirmed by direct import attempts): "
echo "tests.test_ai_gateway_provider_management_pure (4 assertions - the ONE"
echo "module Step 2 touches with zero impure imports: app.ai_gateway.providers.base's"
echo "ConnectionTestResult + ProviderClient.test_connection()'s own default"
echo "not-configured/not-overridden behavior). Also re-ran the full pre-existing"
echo "tests.test_provider_config_pure, tests.test_local_model_policy_pure,"
echo "tests.test_ai_provider_hierarchy_pure, and tests.test_ai_gateway_capabilities_pure"
echo "suites for regression (all pass, confirming Step 2 changed no PURE-testable"
echo "routing/capability/tier/Step-1-config behavior). py_compile ran clean across"
echo "the ENTIRE backend tree (every provider client, the new/changed schemas,"
echo "ui_query.py, routes/ai_gateway.py, both new test files). \`npx tsc --noEmit\`"
echo "ran clean across the entire frontend tree (new types.ts/GatewayDataProvider.ts/"
echo "ApiGatewayProvider.ts/MockGatewayProvider.ts/useProviderConfig.ts/"
echo "ProviderConfigPanel.tsx/AIGatewayProviderDetail.tsx changes)."
echo
echo "NOT run in the authoring sandbox - needs Docker, run for real above:"
echo "tests.test_provider_management_e2e (needs a real Postgres - covers"
echo "ui_query.get_provider_config()'s 'no row yet -> synthesized default' and"
echo "'saved row -> reflected, including updated_by_user_email' paths, the four"
echo "new routes' own logic including 404s for an unregistered provider_key, the"
echo "audit route returning most-recent-first, and the test-connection route being"
echo "reachable by a NON-admin), every *_e2e.py suite in step 4 (needs settings/"
echo "sqlalchemy), and the actual full \`npm run build\` (this sandbox's own rollup"
echo "native-binding limitation - unrelated to this milestone's code - previously"
echo "blocked a full vite build here; \`tsc --noEmit\` was used instead as the"
echo "in-sandbox proxy, same as every prior milestone when Docker isn't available)."
echo
echo "Manual verification checklist (this is the only way to see the real UI):"
echo "-- (a) Log in as a non-admin user, open a provider's detail page - confirm"
echo "--     the Provider Configuration panel renders READ-ONLY (no Save button,"
echo "--     a 'Read-only (admin required to edit)' notice), and Test Connection"
echo "--     still works."
echo "-- (b) Log in as an admin, open the same page - confirm the form is"
echo "--     editable, Save persists (reload the page - values survive), and the"
echo "--     configuration history list grows by one entry per save that actually"
echo "--     changes something."
echo "-- (c) Set an API key, save, then reload - confirm the field shows the"
echo "--     masked placeholder (never the real key), and 'Clear stored key'"
echo "--     actually reverts is_configured()/status back to whatever .env alone"
echo "--     would produce."
echo "-- (d) Click Test Connection for a provider with no credentials configured -"
echo "--     confirm an honest failure message, no crash, no real network call"
echo "--     attempted (is_configured() short-circuits inside test_connection())."
echo "-- (e) As a non-admin, attempt PUT /ai-gateway/providers/claude/config"
echo "--     directly (curl) - confirm 403, not a silent success."
echo
echo "Deferred, disclosed rather than silently dropped - see"
echo "docs/architecture/m8-3-ai-gateway-control-center-plan.md Section 11 for the"
echo "full remaining build order:"
echo "  - Model Role Management UI, Routing Simulator, Capability Viewer changes,"
echo "    Gateway Diagnostics, Premium Approval pre-authorization UI - Steps 3-7."
echo "  - Per-provider retry/timeout override - CEO decision: stays global."
