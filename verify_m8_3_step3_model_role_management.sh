#!/usr/bin/env bash
# M8.3 - AI Gateway Management & Control, STEP 3 ONLY (Model Role
# Management)
#
# Builds on Steps 1-2 (Provider Config resolution/encryption + Provider
# Management UI - approved, verified, committed separately). Step 3 adds
# a DB-backed override layer in front of the CODE-level
# `LOCAL_MODEL_ROLES` table `app.ai_gateway.local_model_policy` already
# had (M8.2 addendum) - per CEO decision #2 (Section 12 of
# docs/architecture/m8-3-ai-gateway-control-center-plan.md): semantic
# roles stay LOCAL-TIER ONLY, wired exclusively into
# `LocalOllamaProviderClient._resolve_model()`. No cloud ProviderClient
# (Claude/OpenAI/Gemini/Groq) is touched by this step - a role assignment
# can never change which PROVIDER a capability routes to.
#
#   Backend:
#   - app/models/ai_model_role.py (NEW), alembic/versions/0031 (NEW) -
#     one new table, `ai_model_roles` (role_name -> model, enabled,
#     updated_by_user_id). A role_name with no row behaves exactly as
#     before this migration - resolves via the pre-existing
#     `LOCAL_MODEL_ROLES` settings-attribute fallback, zero change.
#   - app/ai_gateway/local_model_policy.py: `resolve_local_model()` now
#     checks a DB-backed override (via the new `db_lookup` DI seam,
#     defaulting to the real `_resolve_db_model_for_role()`) for each
#     role in a capability's preference list BEFORE falling back to
#     `LOCAL_MODEL_ROLES`/settings - same "fresh read every call, fail
#     open on DB unavailable" discipline `provider_config.py` (Step 1)
#     established. Also adds `list_model_roles()`/`save_model_role()`/
#     `delete_model_role()` - the write path, no dedicated audit table
#     this step (see `AIModelRole`'s own docstring for why).
#   - app/schemas/ai_gateway.py: ModelRoleWrite/ModelRoleRead.
#   - app/ai_gateway/ui_query.py: get_model_role()/list_model_roles() -
#     thin, read-only projections (this module's own DB read, taking the
#     request-scoped `db: Session`, unlike the fail-open resolution path).
#   - app/api/routes/ai_gateway.py: GET/PUT /ai-gateway/model-roles(/{role_name})
#     and DELETE /ai-gateway/model-roles/{role_name} - all admin-gated
#     (get_current_active_admin, same precedent as Provider Management).
#
#   Frontend:
#   - ai-gateway/types.ts: ModelRole/ModelRoleWrite.
#   - ai-gateway/providers/GatewayDataProvider.ts (+ApiGatewayProvider.ts,
#     +MockGatewayProvider.ts): listModelRoles/saveModelRole/deleteModelRole
#     added to the provider abstraction.
#   - ai-gateway/hooks/useModelRoles.ts (NEW): list-based read/write hook
#     (unlike useProviderConfig's single-row focus - role names are
#     open-ended, so this hook manages the whole list at once).
#   - ai-gateway/components/ModelRoleManagementPanel.tsx (NEW): the
#     editor UI - inline add/edit/delete, admin-only edit (client-side UX
#     gate, backend independently enforces it regardless).
#   - pages/ai-gateway/AIGatewaySettings.tsx: wires the panel in below
#     the pre-existing (M8.2) read-only "Local Model Roles" code-level
#     table, which is unchanged and still shown as-is.
#
# NOT implemented this step (see Section 11's remaining build order):
# Routing Simulator, Provider Capability Viewer changes, Gateway
# Diagnostics, Premium Approval pre-authorization UI. Capability -> role
# PREFERENCE ordering (`CAPABILITY_LOCAL_MODEL_ROLE`) stays a code-level
# table, not exposed for editing this step - see
# `local_model_policy.py`'s own module docstring for why that's a
# business-logic decision, not an ops/config one.
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
echo "=== 2/5: migration - new ai_model_roles table (0031) ==="
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current

echo
echo "=== 3/5: this step's own new test suites ==="
docker compose exec -T backend python -m unittest \
  tests.test_model_role_management_pure \
  tests.test_model_role_management_e2e \
  -v

echo
echo "=== 4/5: FULL regression sweep - local_model_policy.py's resolution order changed, so this is as broad as Steps 1-2's own sweeps ==="
docker compose exec -T backend python -m unittest \
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
echo "tests.test_model_role_management_pure (19 assertions - resolve_local_model()'s"
echo "own db_lookup DI seam exercises DB-override-wins/falls-through-to-settings/"
echo "later-role-in-preference-list precedence for REAL branching logic, plus the"
echo "real _resolve_db_model_for_role() genuinely taking the documented"
echo "'sqlalchemy unavailable -> fail open' path, not a simulated stand-in for it)."
echo "Also re-ran the full pre-existing tests.test_local_model_policy_pure,"
echo "tests.test_provider_config_pure, tests.test_ai_gateway_provider_management_pure,"
echo "tests.test_ai_provider_hierarchy_pure, and tests.test_ai_gateway_capabilities_pure"
echo "suites for regression (90 assertions total, all pass, confirming Step 3 changed"
echo "no PURE-testable settings-fallback/routing/capability/tier/Step-1-Step-2 behavior)."
echo "py_compile ran clean across the ENTIRE backend tree (the new model/migration,"
echo "local_model_policy.py's rewritten resolution order, the new/changed schemas,"
echo "ui_query.py, routes/ai_gateway.py, both new test files)."
echo "\`npx tsc --noEmit\` ran clean across the entire frontend tree (new types.ts/"
echo "GatewayDataProvider.ts/ApiGatewayProvider.ts/MockGatewayProvider.ts/"
echo "useModelRoles.ts/ModelRoleManagementPanel.tsx/AIGatewaySettings.tsx changes)."
echo
echo "NOT run in the authoring sandbox - needs Docker, run for real above:"
echo "tests.test_model_role_management_e2e (needs a real Postgres - covers"
echo "list_model_roles()/save_model_role()/delete_model_role() against a real DB,"
echo "the REAL _resolve_db_model_for_role()/resolve_local_model() DB round trip"
echo "including the 'disabled row is skipped' path, and the three new routes'"
echo "own logic including 400 on a model-less new-role PUT and 404 on a repeat"
echo "DELETE), every *_e2e.py suite in step 4 (needs settings/sqlalchemy), and the"
echo "actual full \`npm run build\` (same sandbox rollup native-binding limitation"
echo "disclosed in every prior milestone's own verify script)."
echo
echo "Manual verification checklist (this is the only way to see the real UI):"
echo "-- (a) Log in as a non-admin, open AI Gateway > Settings - confirm the new"
echo "--     'Model Role Overrides' card renders READ-ONLY (no Add/Edit/Delete"
echo "--     buttons, a 'Read-only (admin required to edit)' notice)."
echo "-- (b) Log in as an admin - Add a role (e.g. role_name='coding',"
echo "--     model='codellama:13b') - confirm it appears in the list, persists"
echo "--     across reload."
echo "-- (c) Edit an existing role's model, Save - confirm the change persists."
echo "-- (d) Disable a role (uncheck Enabled, Save) - confirm the row shows"
echo "--     'Disabled' with a strikethrough model, and (via a Python shell in"
echo "--     the backend container) resolve_local_model() for whichever capability"
echo "--     prefers that role now falls through to the NEXT role/settings value,"
echo "--     exactly as if the row didn't exist."
echo "-- (e) Delete a role - confirm it disappears from the list and"
echo "--     resolve_local_model() reverts to its pre-Step-3 settings-fallback"
echo "--     behavior for that role name."
echo "-- (f) As a non-admin, attempt PUT /ai-gateway/model-roles/research"
echo "--     directly (curl) - confirm 403, not a silent success."
echo "-- (g) Confirm the pre-existing (M8.2) 'Local Model Roles' read-only card"
echo "--     above this one is completely unaffected - still shows the"
echo "--     CODE-level LOCAL_MODEL_ROLES/CAPABILITY_LOCAL_MODEL_ROLE tables."
echo
echo "Deferred, disclosed rather than silently dropped - see"
echo "docs/architecture/m8-3-ai-gateway-control-center-plan.md Section 11 for the"
echo "full remaining build order:"
echo "  - Routing Simulator, Provider Capability Viewer changes, Gateway"
echo "    Diagnostics, Premium Approval pre-authorization UI - Steps 4-7."
echo "  - Capability -> role preference ordering stays code-level, not exposed"
echo "    for editing - a business-logic/routing decision, not an ops/config one."
