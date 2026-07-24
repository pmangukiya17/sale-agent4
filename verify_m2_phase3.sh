#!/usr/bin/env bash
# M2 Phase 3 - Research Intelligence Engine (LLM-backed AIAnalysisEngine)
# + observability UX follow-up (engine badge, zero-document empty state).
#
# CEO-approved scope, per docs/architecture/m2-phase3-intelligence-engine-plan.md:
# - 3A only (LLM-backed AIAnalysisEngine via the first concrete Agent).
# - 3B (signal-adjusted priority) explicitly deferred to a later phase.
#
# Production backend changes:
#   - app/core/config.py: new RESEARCH_ANALYSIS_ENGINE_BACKEND setting,
#     default "deterministic" - zero behavior change until an operator
#     explicitly sets it to "llm".
#   - app/research/analysis/llm_mapping.py (NEW, pure) - parse/validate/
#     extract helpers shared by the agent and the engine.
#   - app/research/analysis/llm_agent.py (NEW) - ResearchAnalysisAgent,
#     the first concrete Agent this codebase has shipped. Registers
#     itself + its ExecutionPolicy + its PromptTemplate at import time.
#   - app/research/analysis/llm_engine.py (NEW) - LLMAnalysisEngine,
#     second AIAnalysisEngine implementation, delegates to
#     ResearchAnalysisAgent via AgentRuntime. Degrades gracefully (never
#     raises) if the agent call fails.
#   - app/research/analysis/registry.py (NEW) - get_analysis_engine(),
#     selected by settings.RESEARCH_ANALYSIS_ENGINE_BACKEND, mirrors
#     app/reply_intelligence/classifiers/registry.py exactly.
#   - app/research/pipeline.py: one call-site change (direct
#     DeterministicAnalysisEngine() construction -> get_analysis_engine()).
#   - app/ai_agents/__init__.py: scope-note update only (no behavior change).
#
# UX-only follow-up (no analysis workflow/engine-selection change):
#   - frontend/src/research/useResearchExecution.ts: exported
#     engineLabel()/engineBadgeTone() (read stored model_used, never
#     current config), and a real explanatory zero-document completion
#     summary instead of "0 document(s) analyzed".
#   - frontend/src/pages/ProspectResearch.tsx: engine Badge on the
#     current Intelligence Snapshot, sourced from that snapshot's own
#     research_job_id -> AIAnalysis.model_used (both already returned by
#     existing routes/schemas - no backend change needed for this).
#   - frontend/src/pages/ResearchJobs.tsx: same engine Badge per job, and
#     an explanatory empty state in the Evidence panel instead of
#     silently showing nothing when raw_document_count is 0.
#
# No database migration - alembic head stays at 0028. No API route
# changes, no schema field changes (IntelligenceSnapshotRead.research_job_id
# and ResearchJobRead.analyses[].model_used already existed).
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
  tests.test_llm_mapping_pure \
  tests.test_research_analysis_agent_pure \
  tests.test_research_analysis_agent_full_chain_e2e \
  tests.test_llm_analysis_engine_e2e \
  tests.test_analysis_engine_registry_e2e \
  -v

echo
echo "=== 4/6: full Research + Discovery regression sweep (default config unchanged, so behavior must be unchanged) ==="
docker compose exec -T backend python -m unittest \
  tests.test_research_workflow_e2e \
  tests.test_ai_execution_platform_e2e \
  tests.test_query_planner_pure \
  tests.test_brave_search_mapping_pure \
  tests.test_search_service_pure \
  tests.test_provider_registry_pure \
  tests.test_discovery_search_service_e2e \
  tests.test_discovery_dedup_pure \
  tests.test_discovery_normalization \
  tests.test_discovery_validation \
  tests.test_discovery_scoring_pure \
  tests.test_discovery_provider_service_pure \
  tests.test_discovery_workflow_e2e \
  tests.test_discovery_job_cancellation \
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
echo "Manual verification checklist (this is the only way to prove the LLM"
echo "engine for real - no real Anthropic API key/network in the authoring"
echo "sandbox):"
echo "-- (a) Confirm default behavior is UNCHANGED: with"
echo "--     RESEARCH_ANALYSIS_ENGINE_BACKEND unset (or 'deterministic'),"
echo "--     run Research on a prospect with pasted text - the Intelligence"
echo "--     Snapshot's engine Badge should read 'Deterministic Engine'."
echo "-- (b) Set ANTHROPIC_API_KEY and RESEARCH_ANALYSIS_ENGINE_BACKEND=llm"
echo "--     as env vars on the backend AND workflow worker containers,"
echo "--     restart them (docker compose up -d --force-recreate backend"
echo "--     workflow_event_dispatcher_worker workflow_step_runner_worker)."
echo "-- (c) On a Prospect's Research page, paste real text about that"
echo "--     company (e.g. copied from their website) and click Run -"
echo "--     zero pasted text still means zero documents regardless of"
echo "--     engine (Research's only document source today is pasted/"
echo "--     uploaded text - see this phase's own disclosed limitation)."
echo "-- (d) Once the job completes, confirm: the Intelligence Snapshot's"
echo "--     engine Badge now reads the real model id (formatted, e.g."
echo "--     'Claude Sonnet 4 5'), with an 'ai' tone (distinct color from"
echo "--     the neutral 'Deterministic Engine' badge); Signal/"
echo "--     Recommendation reasoning reads as natural prose rather than"
echo "--     the deterministic engine's fixed template strings."
echo "-- (e) Confirm Research Jobs page shows the same engine Badge per"
echo "--     job, and that a job run with zero pasted text shows the new"
echo "--     explanatory empty state under 'Evidence (raw documents)'"
echo "--     instead of silently showing nothing."
echo "-- (f) Confirm the Live Workflow Progress screen's completion"
echo "--     summary explains the zero-document case in plain language"
echo "--     instead of '0 document(s) analyzed'."
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - This sandbox has neither Docker, Postgres, sqlalchemy, httpx,"
echo "    nor pydantic_settings installed, and no PyPI/network access to"
echo "    install them - confirmed by direct attempt. tests.test_llm_mapping_pure"
echo "    and tests.test_research_analysis_agent_pure (30 assertions across"
echo "    25 tests) genuinely ARE zero-dependency and WERE executed in the"
echo "    authoring sandbox (all pass) - these are the real proof that"
echo "    ResearchAnalysisAgent's own build_context()/interpret() logic and"
echo "    the shared llm_mapping.py parsing/validation/extraction logic are"
echo "    correct, including a genuine bug caught and fixed this phase (a"
echo "    shallow dict() copy in llm_mapping.py that let two unrelated"
echo "    degraded-output calls silently share and mutate the same list -"
echo "    fixed with copy.deepcopy(), now covered by"
echo "    test_returned_dict_is_a_copy_not_a_shared_reference)."
echo "  - tests.test_research_analysis_agent_full_chain_e2e,"
echo "    tests.test_llm_analysis_engine_e2e, and"
echo "    tests.test_analysis_engine_registry_e2e were only py_compile-"
echo "    checked in the authoring sandbox (they need pydantic_settings"
echo "    and/or sqlalchemy) - run for real in Docker per step 3 above."
echo "  - tsc -b WAS genuinely run in the authoring sandbox and passed"
echo "    clean, zero errors, across all three touched frontend files."
echo "  - No real LLM call has been made anywhere, in any environment, as"
echo "    part of authoring this phase - BraveSearchProvider's own"
echo "    Phase 2 precedent for this exact disclosure applies identically"
echo "    here. Step (b)-(d) above is this phase's first real-call proof."
