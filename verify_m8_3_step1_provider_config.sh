#!/usr/bin/env bash
# M8.3 - AI Gateway Management & Control, STEP 1 ONLY
#
# Per the CEO's explicit instruction: Step 1 is provider_config.py + the
# ai_provider_configs/ai_provider_config_audits migration + encrypted
# credential storage + the ProviderClient refactor + full regression
# verification. Steps 2-7 (Provider Management UI/endpoints, Model Role
# Management, Routing Simulator, Capability Viewer, Diagnostics, Premium
# Approval pre-authorization) are NOT started - see
# docs/architecture/m8-3-ai-gateway-control-center-plan.md Section 11/12
# for the full locked scope and CEO-approved decisions.
#
# Backend changes (all additive; every existing provider client's
# behavior for a deployment that never touches the new DB table is
# BYTE-FOR-BYTE unchanged - that is the one property this whole step is
# built around proving):
#   - app/models/ai_provider_config.py (NEW), app/models/ai_provider_config_audit.py
#     (NEW), alembic/versions/0030 (NEW) - two new tables. A provider_key
#     with no ai_provider_configs row behaves exactly as before this
#     milestone - settings-only, zero change.
#   - app/ai_gateway/provider_config.py (NEW) - resolve_provider_config()
#     (a FRESH DB read every single call, no caching at any scope - the
#     CEO's explicit "must take effect immediately, no restart" requirement)
#     and save_provider_config() (creates/updates one AIProviderConfig row
#     + writes AT MOST ONE AIProviderConfigAudit row per save, never one
#     per field, never a row when nothing changed - the CEO's explicit
#     "lightweight audit history: who/when/what-changed, no rollback"
#     requirement). API keys are encrypted with the SAME Fernet/
#     CREDENTIAL_ENCRYPTION_KEY primitive already used for mailbox OAuth
#     credentials (app/delivery/credentials/postgres_fernet_store.py) -
#     never logged, never returned decrypted by any read API, never
#     written to the audit trail in plaintext (only a "set"/"unset"
#     marker for that one field). extra_settings (JSONB) is the CEO's
#     explicit extensibility requirement - a future provider-specific
#     setting is a new dict key, never a new migration.
#   - app/ai_gateway/providers/claude_client.py, openai_client.py,
#     gemini_client.py (both GeminiProviderClient and
#     GeminiAIStudioProviderClient), groq_client.py, local_client.py,
#     openai_compatible_client.py: every is_configured()/default_model/
#     complete() now reads through resolve_provider_config() instead of
#     settings.<X> directly. No provider-identity branching added
#     anywhere in provider_config.py itself - each client supplies its
#     own settings-derived fallback values, keeping the provider-neutral
#     discipline M-AIGW-1..5 established fully intact.
#
# NOT implemented this step (see Step 2 onward): no HTTP route calls
# save_provider_config() yet (no Provider Management UI/endpoint exists
# yet - that's Step 2), no Test Connection, no per-provider retry/timeout
# override (CEO decision: stays global for now), no Model Role Management
# UI, no Routing Simulator, no Capability Viewer changes, no Diagnostics,
# no Premium Approval pre-authorization.
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
echo "=== 2/5: migration - new ai_provider_configs/ai_provider_config_audits tables (0030) ==="
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current

echo
echo "=== 3/5: this step's own new test suites ==="
docker compose exec -T backend python -m unittest \
  tests.test_provider_config_pure \
  tests.test_provider_config_e2e \
  -v

echo
echo "=== 4/5: FULL regression sweep - every provider client file was touched, so this is deliberately broader than a normal single-feature sweep ==="
docker compose exec -T backend python -m unittest \
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
echo "=== 5/5: frontend build check (unaffected by this backend-only step, run anyway as a cheap regression guard) ==="
docker compose exec -T frontend npx tsc -b --force || (cd frontend && npx tsc -b --force)

echo
echo "ALL AUTOMATED CHECKS COMPLETE"
echo
echo "Genuinely executed in the authoring sandbox (no Docker/network access to"
echo "install sqlalchemy, pydantic_settings, anthropic, openai, or google-genai -"
echo "confirmed by direct import attempts, same as every prior milestone's own"
echo "disclosure): tests.test_provider_config_pure (13 assertions - real Fernet"
echo "encrypt/decrypt round trip via the module's own settings_obj DI seam, plus"
echo "resolve_provider_config()'s fail-open behavior exercised for REAL - this"
echo "sandbox genuinely has no sqlalchemy, so calling it here genuinely takes the"
echo "documented 'DB layer unavailable' branch, not a simulated stand-in for it),"
echo "plus the full pre-existing tests.test_local_model_policy_pure,"
echo "tests.test_ai_provider_hierarchy_pure, and tests.test_ai_gateway_capabilities_pure"
echo "suites re-run for regression (78 assertions total, all pass, confirming the"
echo "provider-client refactor changed no PURE-testable routing/capability/tier"
echo "behavior). py_compile was run clean across the entire backend tree including"
echo "every touched provider client file, both new models, and the new migration."
echo
echo "NOT run in the authoring sandbox - needs Docker, run for real above:"
echo "tests.test_provider_config_e2e (needs a real Postgres - covers the DB"
echo "override/audit-trail round trip, per-field independence, and a REAL"
echo "GroqProviderClient actually reflecting a saved override through its own"
echo "is_configured()/default_model), every *_e2e.py suite in step 4 (needs"
echo "settings/sqlalchemy), and the actual frontend tsc build."
echo
echo "Manual verification checklist (this is the only way to see the real"
echo "encrypted-storage + audit-trail behavior against live Postgres):"
echo "-- (a) With no ai_provider_configs row for any provider_key, confirm every"
echo "--     existing AI Gateway behavior (Research/Outreach, /ai-gateway/*"
echo "--     endpoints from M8.2) is COMPLETELY UNCHANGED from before this step -"
echo "--     this is the one property Step 1 must not regress."
echo "-- (b) In a Python shell inside the backend container, call"
echo "--     save_provider_config(db, 'claude', changed_by_user_id=<a real user"
echo "--     id>, enabled=False); db.commit() - then confirm"
echo "--     GET /ai-gateway/providers/claude now reports status=not_configured"
echo "--     even if ANTHROPIC_API_KEY is set in .env - NO backend restart"
echo "--     performed between the save and this check."
echo "-- (c) Re-enable it (enabled=True) the same way - confirm the provider"
echo "--     reports connected again immediately, still no restart."
echo "-- (d) Inspect the ai_provider_config_audits table directly - confirm"
echo "--     exactly one row per save above, changed_by_user_id set, changed_at"
echo "--     set, field_changes containing {\"enabled\": {\"old\": ..., \"new\": ...}}."
echo "-- (e) Save a provider's api_key via save_provider_config(...) - confirm"
echo "--     ai_provider_configs.encrypted_api_key is NOT the plaintext value,"
echo "--     and ai_provider_config_audits.field_changes for that row contains"
echo "--     only {\"api_key\": {\"old\": \"unset\", \"new\": \"set\"}} - never the"
echo "--     actual key string anywhere in the audits table."
echo
echo "Deferred, disclosed rather than silently dropped - see"
echo "docs/architecture/m8-3-ai-gateway-control-center-plan.md Section 11 for the"
echo "full remaining build order:"
echo "  - No HTTP route/UI calls save_provider_config() yet - Step 2."
echo "  - No Test Connection, no per-provider retry/timeout override (CEO"
echo "    decision: stays global), no Model Role Management UI, no Routing"
echo "    Simulator, no Capability Viewer changes, no Diagnostics, no Premium"
echo "    Approval pre-authorization - Steps 2-7."
