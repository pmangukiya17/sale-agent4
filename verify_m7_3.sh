#!/usr/bin/env bash
# Verification for M7.3 (Supervisor / Orchestrator Layer) against your
# real Docker environment.
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_*.sh before it. M7.3 adds NO new tables/
# migrations/docker-compose services - it is pure application code (a
# new app/supervisor/ package plus additive changes to app/ai_agents/ -
# see below) - `docker compose up --build` is sufficient.
#
# What this script CANNOT verify (disclosed up front):
#   - No concrete Supervisor plan exists yet, and nothing wires
#     SupervisorRuntime into a real Workflow Action or a real
#     WorkflowDefinition trigger - that is explicitly out of scope for
#     M7.3 (future M7.4+ work), matching M7.2's own "infrastructure
#     first, wiring later" precedent.
#   - Persisting/resuming a suspended SupervisionState to the database is
#     NOT built - SupervisionState is designed to be JSON-serializable
#     and carries schema_version/plan_version for when that's built, but
#     no table/migration exists for it in this milestone.
#   - No live AI provider call is made anywhere in this script.
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
echo "=== 2/6: layering boundary matrix ==="
echo "-- workflow_engine/workflow_actions must have zero reference to supervisor/ai_gateway/ai_agents/prompt_builder --"
if docker compose exec -T backend grep -rlE "^\s*(from|import)\s+app\.(ai_gateway|ai_agents|prompt_builder|supervisor)" app/workflow_engine/ app/workflow_actions/; then
  echo "FAILED: workflow_engine/workflow_actions references an AI-stack package"; exit 1
fi
echo "-- app.supervisor must never import app.prompt_builder or app.ai_gateway directly (only via app.ai_agents) --"
if docker compose exec -T backend grep -rlE "^\s*(from|import)\s+app\.(prompt_builder|ai_gateway)" app/supervisor/; then
  echo "FAILED: app.supervisor bypasses AgentRuntime by importing a lower layer directly"; exit 1
fi
echo "-- app.ai_gateway must never import app.ai_agents/app.prompt_builder/app.supervisor (no upward dependency) --"
if docker compose exec -T backend grep -rlE "^\s*(from|import)\s+app\.(ai_agents|prompt_builder|supervisor)" app/ai_gateway/; then
  echo "FAILED: app.ai_gateway has an upward dependency"; exit 1
fi
echo "-- app.prompt_builder must never import app.ai_agents or app.supervisor --"
if docker compose exec -T backend grep -rlE "^\s*(from|import)\s+app\.(ai_agents|supervisor)" app/prompt_builder/; then
  echo "FAILED: app.prompt_builder has an upward dependency"; exit 1
fi
echo "-- app.ai_agents must never import app.supervisor (an Agent must never know a Supervisor exists) --"
if docker compose exec -T backend grep -rlE "^\s*(from|import)\s+app\.supervisor" app/ai_agents/; then
  echo "FAILED: app.ai_agents references app.supervisor"; exit 1
fi
echo "-- only app/ai_gateway/providers/*.py may import anthropic/openai/google.genai directly (unchanged from M7.2) --"
if docker compose exec -T backend sh -c "grep -rlE '^\s*(import|from)\s+(anthropic|openai(\.| |\$)|google\.genai)' app/ | grep -v '^app/ai_gateway/providers/'"; then
  echo "FAILED: a file outside app/ai_gateway/providers/ imports a provider SDK directly"; exit 1
fi
echo "confirmed: every M7.3 layering boundary holds"

echo
echo "=== 3/6: M7.3 Supervisor test suite (real execution, local test doubles - no DB, no live provider) ==="
docker compose exec -T backend python -m unittest tests.test_supervisor_e2e -v

echo
echo "=== 4/6: M7.2 AI Execution Platform suite - regression check for the AgentRuntime refactor (metadata + RETRY loop) ==="
docker compose exec -T backend python -m unittest tests.test_ai_execution_platform_e2e -v

echo
echo "=== 5/6: full M7.1/M7.2 regression - workflow engine + pilot workflow suites still green ==="
docker compose exec -T backend python -m unittest tests.test_action_registry tests.test_workflow_definition_validation tests.test_workflow_events tests.test_workflow_definitions tests.test_workflow_instance_models tests.test_event_dispatcher_worker tests.test_step_runner_worker tests.test_pilot_workflow_e2e -v

echo
echo "=== 6/6: SQLAlchemy mapper configuration (M7.3 added zero models/migrations, so this should be an unaffected no-op check) ==="
docker compose exec -T backend python -c "
from app.db import base as _base
from sqlalchemy.orm import configure_mappers
configure_mappers()
print('All mappers configured successfully - every relationship() resolved.')
"

echo
echo "ALL CHECKS COMPLETE"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - Zero concrete Supervisor plans exist, and nothing wires SupervisorRuntime into a real Workflow Action or"
echo "    WorkflowDefinition trigger yet - explicitly future (M7.4+) work."
echo "  - SupervisionState persistence/resumption is not built - only the JSON-serializable, versioned shape is ready"
echo "    for it (schema_version/plan_version/created_at/updated_at)."
echo "  - The per-plan agent allowlist and max-depth/max-cost guards are exercised only against test doubles here -"
echo "    no real Planning Agent or LLM-driven Supervisor exists yet to validate against a real hallucinated plan."
echo "  - Log correlation via ExecutionIdLogFilter is wired onto the root logger's handlers in app/main.py, but this"
echo "    script does not assert on actual log output containing execution_id - a manual 'docker compose logs backend'"
echo "    inspection during a real Supervisor run (once one exists) would be needed to see it end to end."
