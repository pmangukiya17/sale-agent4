#!/usr/bin/env bash
# Verification for M7.4 (Autonomous Multi-Agent Workflows - the Workflow
# <-> Supervisor bridge) against your real Docker environment.
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_*.sh before it. M7.4 adds NO new tables/
# migrations/docker-compose services - it is pure application code (a new
# app/supervisor/serialization.py, a new
# app/workflow_actions/supervisor_invocation_action.py, an additive field
# on ActionInput, and a versioned rewrite of app/supervisor/registry.py) -
# `docker compose up --build` is sufficient.
#
# What this script CANNOT verify (disclosed up front):
#   - No concrete Supervisor plan exists yet, and nothing wires
#     SupervisorInvocationAction into a real WorkflowDefinition's
#     step_graph as part of an actual business process - explicitly out
#     of scope for M7.4 (future work), matching M7.2/M7.3's own
#     "infrastructure first, a real business plan later" precedent. (A
#     synthetic step_graph IS exercised for real by
#     tests.test_step_runner_worker's own
#     test_supervisor_wait_suspends_without_incrementing_attempts - see
#     step 5/6 below - but that is a regression fixture, not a real plan.)
#   - WAIT resumption has no automated waker yet, for ANY
#     ResumeTriggerType (TIME included - this is deliberate, see
#     supervisor_invocation_action.py's own docstring for why TIME is not
#     special-cased as "pollable"). A Supervisor-driven WAIT now suspends
#     correctly (ActionOutcome.PENDING, WorkflowInstanceStatus.WAITING,
#     zero attempts consumed - the exact regression
#     test_supervisor_wait_suspends_without_incrementing_attempts locks
#     in), but nothing in this script - or in the shipped code - ever
#     flips such an instance back to RUNNING. That remains the deferred
#     Event Dispatcher extension (matching a dynamically-supplied resume
#     expectation from WorkflowInstance.context, instead of only a
#     statically-declared step_def.action_config.event_type). This is a
#     disclosed, deliberate scope boundary, not an oversight: this
#     milestone's revised job was to make SUSPENSION correct, not to
#     also build automated RESUMPTION.
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
echo "=== 2/6: layering boundary matrix (M7.4-updated) ==="
echo "-- app/workflow_engine/ must STILL have zero reference to supervisor/ai_gateway/ai_agents/prompt_builder/workflow_actions --"
if docker compose exec -T backend grep -rlE "^\s*(from|import)\s+app\.(ai_gateway|ai_agents|prompt_builder|supervisor|workflow_actions)" app/workflow_engine/; then
  echo "FAILED: workflow_engine references an AI-stack or domain package - the engine must stay generic"; exit 1
fi
echo "-- app/workflow_actions/: exactly one file (supervisor_invocation_action.py) may import app.supervisor --"
matches=$(docker compose exec -T backend grep -rlE "^\s*(from|import)\s+app\.supervisor" app/workflow_actions/ | tr -d '\r')
if [ "$matches" != "app/workflow_actions/supervisor_invocation_action.py" ]; then
  echo "FAILED: unexpected set of files importing app.supervisor from app.workflow_actions:"; echo "$matches"; exit 1
fi
echo "-- app/workflow_actions/ must never import app.ai_gateway/app.ai_agents/app.prompt_builder directly (only via app.supervisor) --"
if docker compose exec -T backend grep -rlE "^\s*(from|import)\s+app\.(ai_gateway|ai_agents|prompt_builder)" app/workflow_actions/; then
  echo "FAILED: app.workflow_actions bypasses SupervisorRuntime/AgentRuntime by importing a lower layer directly"; exit 1
fi
echo "-- app.supervisor must never import app.workflow_actions or app.workflow_engine (dependency arrow points one way only) --"
if docker compose exec -T backend grep -rlE "^\s*(from|import)\s+app\.(workflow_actions|workflow_engine)" app/supervisor/; then
  echo "FAILED: app.supervisor has a reverse dependency on the engine/bridge layer above it"; exit 1
fi
echo "-- app.supervisor must never import app.prompt_builder or app.ai_gateway directly (only via app.ai_agents) - unchanged M7.3 rule --"
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
echo "confirmed: every M7.4 layering boundary holds"

echo
echo "=== 3/6: M7.4 test suite (real execution, local test doubles - no DB, no live provider) ==="
docker compose exec -T backend python -m unittest tests.test_supervisor_invocation_action_e2e -v

echo
echo "=== 4/6: M7.3 Supervisor suite - regression check for the versioned registry rewrite (get_supervisor/register_supervisor signature change) ==="
docker compose exec -T backend python -m unittest tests.test_supervisor_e2e -v

echo
echo "=== 5/6: M7.2 AI Execution Platform suite + full M7.1 regression - workflow engine + pilot workflow suites still green after ActionInput.action_config addition. This INCLUDES tests.test_step_runner_worker's own test_supervisor_wait_suspends_without_incrementing_attempts - a real, DB-backed WorkflowInstance/WorkflowStepInvocation regression proving a Supervisor WAIT decision produces exactly one PENDING attempt (never a second, retried one) and survives the round trip through the real context JSONB column while WorkflowInstanceStatus stays WAITING ==="
docker compose exec -T backend python -m unittest tests.test_ai_execution_platform_e2e tests.test_action_registry tests.test_workflow_definition_validation tests.test_workflow_events tests.test_workflow_definitions tests.test_workflow_instance_models tests.test_event_dispatcher_worker tests.test_step_runner_worker tests.test_pilot_workflow_e2e -v

echo
echo "=== 6/6: SQLAlchemy mapper configuration (M7.4 added zero models/migrations, so this should be an unaffected no-op check) ==="
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
echo "  - Zero concrete Supervisor plans exist as part of a real business process, and nothing wires"
echo "    SupervisorInvocationAction into a real WorkflowDefinition's step_graph for actual production use -"
echo "    explicitly future work, the same 'infrastructure first' scope discipline as M7.2/M7.3. (Step 5/6 above DOES"
echo "    exercise a real, DB-backed WorkflowInstance through SupervisorInvocationAction via"
echo "    step_runner_worker.process_instance() - but only as a regression fixture, not a real plan.)"
echo "  - SupervisionState still has no table of its own - app.supervisor.serialization only serializes INTO a"
echo "    WorkflowInstance's existing opaque context column, never independently persisted/queryable."
echo "  - WAIT now suspends correctly and durably (PENDING/WAITING, zero attempts consumed) but has NO automated"
echo "    resume path yet, for any ResumeTriggerType - see supervisor_invocation_action.py's own docstring. That"
echo "    remains the deferred Event Dispatcher extension (dynamic resume-expectation matching), unchanged from"
echo "    before this correction - this milestone's revised scope was to fix SUSPENSION semantics only."
echo "  - Nested Supervisor-to-Supervisor composition remains unbuilt by design - Workflow-mediated composition is"
echo "    now an explicit architectural rule (see app/supervisor/__init__.py's own constraint 4)."
