#!/usr/bin/env bash
# M8.2 - AI Gateway Backend Integration
#
# Replaces the M8.1 mock GatewayDataProvider with a real ApiGatewayProvider
# calling new, read-only /ai-gateway/* endpoints, and adds task-based local
# model routing (semantic roles: capability -> role -> configured model),
# per the CEO's approved refinement over the original default/secondary
# proposal.
#
# Backend changes (all additive):
#   - app/core/config.py: LOCAL_MODEL_SECONDARY_MODEL (NEW setting).
#   - app/ai_gateway/local_model_policy.py (NEW) - the single centralized
#     capability -> semantic role -> configured local model resolver.
#     LOCAL_MODEL_ROLES ("research"/"writing" -> settings attribute name),
#     CAPABILITY_LOCAL_MODEL_ROLE (capability -> ordered role preference).
#   - app/ai_gateway/providers/openai_compatible_client.py: new
#     `_resolve_model()` hook (base behavior unchanged: `request.model or
#     self.default_model` - GroqProviderClient inherits this unmodified).
#   - app/ai_gateway/providers/local_client.py: overrides `_resolve_model()`
#     to call local_model_policy.resolve_local_model() - the ONLY provider
#     with task-based model selection.
#   - app/models/ai_request_log.py (NEW), alembic/versions/0029 (NEW) - one
#     new table, ai_request_logs, durably persisting every AI Gateway call
#     (request_log.py's own docstring had already anticipated this exact
#     migration).
#   - app/ai_gateway/request_log.py: log_ai_request() gains a second,
#     additive side effect (best-effort DB insert via its own short-lived
#     SessionLocal session, wrapped in try/except - never breaks the real
#     Gateway call on a logging failure). Signature and all 3 call sites
#     in client.py are UNCHANGED.
#   - app/ai_gateway/ui_query.py (NEW) - the read-only query layer behind
#     the new routes: list_providers/get_provider (live registry/tiers/
#     capabilities reads, no DB), get_overview/list_activity/list_approvals
#     (AIRequestLog, isolated per calling user's own companies),
#     list_routing_decisions (a REAL-TIME POLICY PREVIEW via
#     ProviderRouter.select() - this codebase persists only a final
#     per-attempt-sequence outcome, never a full historical routing chain,
#     so Routing recomputes the live policy fresh rather than replaying
#     one), get_settings (live projection of AI_MODE/premium-approval
#     gate/local model roles - read-only, no persistence).
#   - app/schemas/ai_gateway.py (NEW), app/api/routes/ai_gateway.py (NEW) -
#     7 new GET routes under /ai-gateway/*, workspace-scoped
#     (current_user only, matching workspace_settings.py's precedent, not
#     /company-profiles/{id}/...).
#   - app/main.py: registers the new router.
#
# Frontend changes (M8.1's UI architecture is untouched - every page/
# component/hook signature from that milestone is unchanged; this is
# purely a data-source swap):
#   - frontend/src/ai-gateway/providers/ApiGatewayProvider.ts (NEW) - the
#     real GatewayDataProvider implementation, translating the backend's
#     snake_case JSON into the existing camelCase types.ts contract.
#   - frontend/src/ai-gateway/providers/GatewayDataProviderContext.tsx: one
#     line changed - `new ApiGatewayProvider(apiClient)` instead of `new
#     MockGatewayProvider()` (MockGatewayProvider.ts is kept, unused, as an
#     offline-dev fixture).
#   - frontend/src/ai-gateway/types.ts,
#     .../providers/GatewayDataProvider.ts: ADDITIVE only - one new
#     GatewaySettings type and one new getSettings() interface method; no
#     existing type or method signature changed.
#   - frontend/src/ai-gateway/hooks/useGatewaySettings.ts (NEW) - backs the
#     Settings page, which had no hook at all in M8.1 (it was a static
#     placeholder) - nothing to keep "unchanged" there, this is new.
#   - frontend/src/pages/ai-gateway/AIGatewaySettings.tsx: now renders real
#     read-only settings instead of a pure placeholder. Every other M8.1
#     AI Gateway page file is UNCHANGED - they already consumed the
#     GatewayDataProvider interface, never the mock directly.
#
# NOT implemented this milestone (see M8.2 approved scope): provider
# configuration, settings persistence, approval ACTIONS (Approvals stays
# read-only - see ApprovalRequestRead's own docstring for why there is no
# durable "pending" queue to act on in this codebase), charts, live
# updates, polling, WebSockets.
#
# --- Regression-sweep fixes (post first real Docker run of this script) ---
#   - tests/test_ai_provider_hierarchy_e2e.py::TestCapabilityAwareRouting had
#     two stale, hardcoded assertions (from before M-AIGW-3 added
#     "gemini_ai_studio" to CAPABILITY_PROVIDER_PREFERENCE's default list -
#     this file was only py_compile-checked, never actually run, between
#     M-AIGW-3 and this milestone's step 4). Both assertions now DERIVE
#     their expected chain/premium/excluded sets live from
#     CAPABILITY_PROVIDER_PREFERENCE + tiers.partition() + each registered
#     provider's own declared capabilities, instead of a hardcoded provider
#     list - a future provider addition changes what this test expects
#     automatically rather than silently breaking it again.
#   - app/ai_gateway/request_log.py's `_persist_ai_request_log()` now also
#     imports `app.db.base` (registers every model before configure_mappers()
#     runs) before touching AIRequestLog - fixes a genuine M8.2 regression:
#     this function's new DB write was the first real ORM operation several
#     e2e test files (which never previously needed the model registry
#     loaded) triggered, so CompanyProfile's lazy `relationship()` string
#     reference couldn't resolve ("CompanyProfile failed to locate a name").
#     Same fix pattern already used by every worker entrypoint in this
#     codebase (app/notifications/worker.py, app/delivery/worker.py, etc.)
#     and by the earlier Phase 3 e2e mapper-registration fix.
#   - The "approval_required: True -> False" observation was NOT a code
#     regression: with LOCAL_MODEL_BASE_URL set (this milestone's own new
#     Ollama config), local_ollama.is_configured() is True, so
#     AIGateway.preflight()'s chain_has_configured_candidate check is
#     already satisfied before gemini_ai_studio is ever considered -
#     exactly the intended "local tier configured -> skip premium approval"
#     behavior (see verify_m11_ai_provider_hierarchy.sh's own manual
#     checklist item (f)). No test asserted the old "True" value, so no
#     test change was needed for this one.
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
echo "=== 2/6: migration - new ai_request_logs table (0029) ==="
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current

echo
echo "=== 3/6: this milestone's own new test suites ==="
docker compose exec -T backend python -m unittest \
  tests.test_local_model_policy_pure \
  tests.test_ai_gateway_ui_query_e2e \
  -v

echo
echo "=== 4/6: AI Gateway regression sweep (M11/M-AIGW-* suites must be unaffected by the _resolve_model() hook + local_model_policy addition) ==="
docker compose exec -T backend python -m unittest \
  tests.test_ai_provider_hierarchy_pure \
  tests.test_ai_provider_hierarchy_e2e \
  tests.test_ai_gateway_capabilities_pure \
  -v

echo
echo "=== 5/6: frontend build check (tsc -b) ==="
docker compose exec -T frontend npx tsc -b --force || (cd frontend && npx tsc -b --force)

echo
echo "=== 6/6: manual endpoint smoke (requires a logged-in JWT - see auth.py) ==="
echo "curl -H \"Authorization: Bearer \$TOKEN\" http://localhost:8000/api/v1/ai-gateway/overview"
echo "curl -H \"Authorization: Bearer \$TOKEN\" http://localhost:8000/api/v1/ai-gateway/providers"
echo "curl -H \"Authorization: Bearer \$TOKEN\" http://localhost:8000/api/v1/ai-gateway/providers/local_ollama"
echo "curl -H \"Authorization: Bearer \$TOKEN\" http://localhost:8000/api/v1/ai-gateway/activity"
echo "curl -H \"Authorization: Bearer \$TOKEN\" http://localhost:8000/api/v1/ai-gateway/approvals"
echo "curl -H \"Authorization: Bearer \$TOKEN\" http://localhost:8000/api/v1/ai-gateway/routing"
echo "curl -H \"Authorization: Bearer \$TOKEN\" http://localhost:8000/api/v1/ai-gateway/settings"

echo
echo "ALL AUTOMATED CHECKS COMPLETE"
echo
echo "Genuinely executed in the authoring sandbox (no Docker/network access to"
echo "install sqlalchemy or pydantic_settings - confirmed by direct import AND"
echo "a direct 'pip install sqlalchemy pydantic-settings --break-system-packages'"
echo "attempt, both failing the same way every prior milestone's own disclosure"
echo "in this project already documents): tests.test_local_model_policy_pure"
echo "(11 assertions) via resolve_local_model()'s own settings_obj DI seam, plus"
echo "the full pre-existing tests.test_ai_provider_hierarchy_pure and"
echo "tests.test_ai_gateway_capabilities_pure suites re-run for regression (65"
echo "assertions total, all pass, confirming the _resolve_model() refactor did"
echo "not change OpenAICompatibleProviderClient/GroqProviderClient behavior)."
echo "py_compile was run clean across every new/touched backend file including"
echo "the new migration. tsc -b WAS genuinely run in the authoring sandbox and"
echo "passed clean, zero errors, across the full frontend (all pre-existing"
echo "AI Gateway pages plus the new ApiGatewayProvider/useGatewaySettings)."
echo
echo "NOT run in the authoring sandbox - needs Docker, run for real above:"
echo "tests.test_ai_gateway_ui_query_e2e (needs a real Postgres - covers"
echo "per-user isolation, Overview aggregation, Activity ordering/limit,"
echo "Approvals' error_type filter, Settings reflecting real config),"
echo "tests.test_ai_provider_hierarchy_e2e (needs settings/pydantic_settings),"
echo "and the actual frontend dev server / vite build (this sandbox's"
echo "node_modules contains a macOS-only native rollup binary - see the M8.1"
echo "handoff's own disclosure of this exact constraint)."
echo
echo "Manual verification checklist (this is the only way to see the real"
echo "8-page AI Gateway UI end to end against live data):"
echo "-- (a) Log in, open /ai-gateway. Confirm Overview's 7 KPIs render (no"
echo "--     'Could not load' error) - Gateway Health should read 'Healthy' if"
echo "--     ANY provider (even just local_ollama with LOCAL_MODEL_BASE_URL"
echo "--     set) is configured, 'Down' if none are."
echo "-- (b) Open /ai-gateway/providers - confirm all 6 providers render with"
echo "--     correct tier/status; local_ollama should show 'Connected' with"
echo "--     LOCAL_MODEL_BASE_URL=http://127.0.0.1:11434/v1 set."
echo "-- (c) Click into a provider (e.g. local_ollama) - confirm the detail"
echo "--     page shows its capabilities and default model (qwen3:8b)."
echo "-- (d) Run a real Research analysis (RESEARCH_ANALYSIS_ENGINE_BACKEND=llm,"
echo "--     a local Ollama server running qwen3:8b reachable at"
echo "--     LOCAL_MODEL_BASE_URL) - confirm a new row appears in"
echo "--     /ai-gateway/activity with provider 'local_ollama' and model"
echo "--     'qwen3:8b', and that Overview's Today's Requests/Success Rate"
echo "--     update to reflect it."
echo "-- (e) Run a real Outreach email draft the same way - confirm its"
echo "--     Activity row's model is 'llama3.1:8b' (the 'writing' role),"
echo "--     NOT 'qwen3:8b' - this is the concrete, observable proof the"
echo "--     task-based local model routing is actually wired end to end."
echo "-- (f) If LOCAL_MODEL_SECONDARY_MODEL is unset, re-run (e) - confirm the"
echo "--     model falls back to qwen3:8b instead of erroring."
echo "-- (g) Open /ai-gateway/routing - confirm both live capabilities"
echo "--     (research_analysis, outreach_email_generation) show a routing"
echo "--     preview reflecting current provider configuration."
echo "-- (h) Open /ai-gateway/settings - confirm AI mode/premium-approval gate/"
echo "--     capability -> provider preference/local model roles all match"
echo "--     the real .env values."
echo "-- (i) With AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL=true and no local/free"
echo "--     provider configured, trigger a capability that needs premium -"
echo "--     confirm it appears in /ai-gateway/approvals (read-only; Approve/"
echo "--     Reject show a 'not yet implemented' toast, unchanged from M8.1)."
echo
echo "Deferred, disclosed rather than silently dropped (see each schema's own"
echo "docstring in app/schemas/ai_gateway.py):"
echo "  - Provider configuration, settings persistence, and approval actions -"
echo "    explicitly out of scope per the approved M8.2 goals."
echo "  - Routing is a real-time POLICY PREVIEW, not a replay of one specific"
echo "    past request's actual attempted chain - this codebase's AIRequestLog"
echo "    persists only a final outcome per attempt sequence, never the full"
echo "    ordered sequence AIGateway._walk() may have tried first."
echo "  - Approvals reflects PAST premium-approval-required events, not a live"
echo "    blocking queue - this codebase's gate is a synchronous pre-flight"
echo "    check (AIGateway.preflight()/PremiumApprovalRequiredError), not a"
echo "    durable, still-actionable request a human can act on later."
echo "  - Provider-level requests_today/avg_latency_ms are aggregated GLOBALLY"
echo "    (not per-user) - provider credentials are instance-wide"
echo "    app.core.config.settings, not per-company data."
