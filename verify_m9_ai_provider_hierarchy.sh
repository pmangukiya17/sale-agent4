#!/usr/bin/env bash
# M9 - AI Provider Hierarchy (Local -> Free -> Premium)
#
# CEO-directed architecture milestone: extends the existing AI Gateway
# (M7.2/M7.3, unchanged in shape - see
# docs/architecture/ai-provider-hierarchy-v3-plan.md for the full review
# and design) with a configurable, tier-aware provider hierarchy - Local
# (Ollama-compatible) -> Free (Groq) -> Premium (Claude/OpenAI/Gemini) -
# four AI Modes (local_only / hybrid_recommended / automatic_premium /
# premium_only), a "STOP, ask user" approval gate before any premium call,
# a heuristic confidence-assessment module, pre-call cost estimation, and
# structured request logging.
#
# Backend changes (all additive - see each file's own M9 docstring):
#   - app/core/config.py: AI_MODE, AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL
#     (default True - see its own docstring for why this is safe:
#     Research's "llm" engine is itself still off by default), LOCAL_MODEL_*,
#     GROQ_* settings.
#   - app/ai_gateway/tiers.py (NEW) - PROVIDER_TIER_REGISTRY, partition().
#   - app/ai_gateway/providers/openai_compatible_client.py (NEW) - generic
#     base class reusing the `openai` SDK (already pinned) against a
#     configurable base_url - no new third-party dependency.
#   - app/ai_gateway/providers/local_client.py,
#     app/ai_gateway/providers/groq_client.py (NEW) - thin subclasses.
#   - app/ai_gateway/providers/registry.py: two new registry entries.
#   - app/ai_gateway/router.py: RoutingDecision gains `premium`; primary
#     is now optional (empty chain is a real, valid state);
#     CAPABILITY_PROVIDER_PREFERENCE replaces the old single-provider
#     ROUTING_POLICY as the real routing config; ROUTING_POLICY itself is
#     KEPT, repurposed as an empty-by-default TEST-ONLY override seam
#     (existing tests unmodified in spirit, one file's cleanup bug fixed -
#     see that file's own comment).
#   - app/ai_gateway/errors.py: PremiumApprovalRequiredError.
#   - app/ai_gateway/accounting.py: estimate_pre_call_cost_usd().
#   - app/ai_gateway/confidence.py (NEW) - heuristic assess_complexity().
#   - app/ai_gateway/request.py: GatewayRequest.premium_approved (default
#     False - zero behavior change for any existing caller).
#   - app/ai_gateway/client.py: the premium-approval gate itself, plus
#     structured request logging (app/ai_gateway/request_log.py, NEW).
#   - app/ai_agents/base.py: AgentExecutionResult.premium_approval (NEW,
#     optional field) + PremiumApprovalContext.
#   - app/ai_agents/runtime.py: one narrow `except
#     PremiumApprovalRequiredError` clause, before the existing generic
#     GatewayError catch - populates the new field without changing any
#     other behavior.
#   - app/research/analysis/base.py, deterministic_stub.py, llm_engine.py:
#     `analyze()` gains `premium_approved: bool = False` (default
#     preserves every existing call site); LLMAnalysisEngine surfaces a
#     distinct, greppable degraded outcome when approval is needed instead
#     of a generic failure.
#   - app/research/pipeline.py: extracts `premium_approved` from run_input
#     (never leaks into a provider's own source_spec).
#   - app/research/ai_preflight.py (NEW) - pre-flight check the frontend
#     calls BEFORE submitting a run, so the approval dialog can be shown
#     at submission time (disclosed, deliberate scope: a pre-flight check,
#     NOT a mid-workflow pause/resume - see that module's own docstring
#     for why).
#   - app/schemas/research_request.py: ResearchRequestRunBody.premium_approved,
#     new AIPreflightResult schema.
#   - app/api/routes/research_requests.py: new POST .../ai-preflight route.
#
# Frontend changes:
#   - frontend/src/research/PremiumApprovalDialog.tsx (NEW) - the Yes/No
#     approval dialog (reasons + cost estimate), built on the existing
#     Modal primitive.
#   - frontend/src/pages/ProspectResearch.tsx: calls ai-preflight before
#     submitting a run; shows the dialog if approval is required.
#
# No database migration - alembic head is unchanged. Per-workspace AI
# settings persistence and a full mid-workflow pause/resume mechanism are
# BOTH explicitly deferred (see the design doc's Section 3.3 and this
# script's own disclosure above) - not silently dropped.
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
echo "=== 2/6: migration regression guard - no schema change this milestone ==="
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current

echo
echo "=== 3/6: this milestone's own new test suites ==="
docker compose exec -T backend python -m unittest \
  tests.test_ai_provider_hierarchy_pure \
  tests.test_ai_provider_hierarchy_e2e \
  -v

echo
echo "=== 4/6: full AI Execution Platform + Research regression sweep (default config unchanged for every OTHER capability, so behavior there must be unchanged) ==="
docker compose exec -T backend python -m unittest \
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
echo "=== 5/6: frontend build check (tsc -b) ==="
docker compose exec -T frontend npx tsc -b --force || (cd frontend && npx tsc -b --force)

echo
echo "=== 6/6: full smoke test (must pass end-to-end with no regressions) ==="
docker compose exec -T backend python smoke_test.py || python3 smoke_test.py

echo
echo "ALL AUTOMATED CHECKS COMPLETE"
echo
echo "Genuinely executed in the authoring sandbox (no Docker/pydantic_settings/"
echo "sqlalchemy - confirmed by direct import + pip install attempts, same as"
echo "every prior milestone's disclosure): tests.test_ai_provider_hierarchy_pure"
echo "(25 assertions, all pass) - covers tiers.py, confidence.py, router.py's"
echo "RoutingDecision/_build_decision for all four AI Modes (including the"
echo "backward-compatibility case: a claude-only preference list under"
echo "hybrid_recommended correctly gates behind approval rather than either"
echo "failing or silently bypassing the gate), and accounting.py's pre-call"
echo "cost estimate. py_compile was run clean across the entire backend app"
echo "tree plus every touched/new test file. tsc -b WAS genuinely run in the"
echo "authoring sandbox and passed clean, zero errors."
echo
echo "NOT run in the authoring sandbox - needs Docker, run for real above:"
echo "tests.test_ai_provider_hierarchy_e2e (needs settings/pydantic_settings -"
echo "exercises AIGateway.complete()'s premium-approval gate end to end with"
echo "fake ProviderClients, mirroring test_ai_execution_platform_e2e.py's own"
echo "provider_lookup DI seam), and every other DB/settings-backed suite"
echo "listed in step 3/4."
echo
echo "Manual verification checklist (this is the only way to prove the real"
echo "provider hierarchy end to end - no real Ollama/Groq/Claude network"
echo "access in the authoring sandbox):"
echo "-- (a) Confirm default behavior for every OTHER AI-backed feature is"
echo "--     UNCHANGED: with no LOCAL_MODEL_BASE_URL/GROQ_API_KEY set and"
echo "--     RESEARCH_ANALYSIS_ENGINE_BACKEND=deterministic (the existing"
echo "--     default), Research still runs exactly as before M9."
echo "-- (b) Set RESEARCH_ANALYSIS_ENGINE_BACKEND=llm and ANTHROPIC_API_KEY,"
echo "--     leave LOCAL_MODEL_BASE_URL/GROQ_API_KEY unset (AI_MODE defaults"
echo "--     to hybrid_recommended, AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL"
echo "--     defaults true). Run Research on a prospect with pasted text -"
echo "--     the Premium Approval dialog should appear BEFORE the run is"
echo "--     submitted, showing 'Claude' as the candidate provider."
echo "-- (c) Click 'Yes' - confirm the run proceeds and completes with a"
echo "--     real Claude-produced Intelligence Snapshot, same as pre-M9's"
echo "--     'llm' engine behavior once approved."
echo "-- (d) Click 'No' (or start a fresh run and decline) - confirm the run"
echo "--     completes without AI escalation, and the stored AIAnalysis rows'"
echo "--     reasoning field explains a premium approval was needed and"
echo "--     declined (prefixed 'PREMIUM_APPROVAL_REQUIRED:' - see"
echo "--     llm_engine.py's own constant)."
echo "-- (e) Set AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL=false, re-run - confirm"
echo "--     Claude is now called automatically with NO dialog shown (the"
echo "--     exact pre-M9 behavior, byte for byte)."
echo "-- (f) If a real Ollama/vLLM/LM Studio instance is available, set"
echo "--     LOCAL_MODEL_BASE_URL to its OpenAI-compatible endpoint (e.g."
echo "--     http://localhost:11434/v1 for Ollama) and LOCAL_MODEL_DEFAULT_MODEL"
echo "--     to a pulled model name - confirm Research now completes via the"
echo "--     local model with NO approval prompt at all (local tier, always"
echo "--     auto-attempted first)."
echo
echo "Deferred, disclosed rather than silently dropped:"
echo "  - Per-workspace persisted AI settings (Mode, budget, provider"
echo "    priority) - AI_MODE etc. are GLOBAL settings this milestone, per"
echo "    the design doc's own Section 3.3 (no workspace/multi-user model"
echo "    exists yet to hang per-tenant config off of)."
echo "  - True mid-workflow pause/resume for premium approval - this"
echo "    milestone ships a PRE-FLIGHT check instead (approval decided"
echo "    before a run is submitted, not mid-run) - see"
echo "    app/research/ai_preflight.py's own docstring for the full"
echo "    reasoning. A run whose approval need changes between preflight"
echo "    and execution degrades to the existing 'AI analysis failed'-"
echo "    shaped outcome, never a silent premium call, never a crash."
echo "  - A real cost-observability dashboard / per-tenant budget ledger -"
echo "    same disclosed gap as the prior AI-layer architecture review"
echo "    (docs/architecture/ai-layer-architecture-review-v2.md) - the"
echo "    pre-call cost estimate here is a heuristic for the approval"
echo "    prompt only, not a persisted, aggregated spend total."
