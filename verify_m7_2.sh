#!/usr/bin/env bash
# Verification for M7.2 (AI Execution Platform: AI Gateway + Prompt
# Builder + AI Agent Runtime, including the two approved refinements)
# against your real Docker environment.
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_m7_1_*.sh/verify_m6_*.sh before it. M7.2 adds NO
# new tables/migrations/docker-compose services - it is pure application
# code (new packages app/ai_gateway/, app/prompt_builder/, app/ai_agents/,
# plus three new pinned dependencies in requirements.txt) - so `docker
# compose up --build` is sufficient; no fresh database is required.
#
# What this script CANNOT verify (disclosed up front, not glossed over):
#   - No live call to a real Claude/OpenAI/Gemini API is made anywhere in
#     this script - there is no API key configured in this project by
#     default, and this milestone's own scope never required one. Every
#     ProviderClient's translation logic (claude_client.py/openai_client.py/
#     gemini_client.py) is exercised by real SDK object construction where
#     possible, but the actual HTTP round-trip to each provider has never
#     been executed against a live account.
#   - No Workflow Action wires AgentRuntime into a real workflow step yet -
#     that is explicitly out of scope for M7.2 (see step 6 below, which
#     confirms this boundary rather than testing an integration that
#     deliberately does not exist yet).
set -euo pipefail

echo "=== 1/7: rebuild + boot (pulls in the 3 new pinned SDKs from requirements.txt) ==="
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
echo "=== 2/7: the 3 new provider SDKs actually installed inside the backend image ==="
docker compose exec -T backend python -c "
import anthropic, openai
from google import genai
print('anthropic', anthropic.__version__)
print('openai', openai.__version__)
print('google-genai import OK (module has no __version__ attribute on all releases, so this import succeeding is the check)')
"

echo
echo "=== 3/7: domain-boundary grep - only app/ai_gateway/providers/*.py may import anthropic/openai/google.genai ==="
echo "-- files that DO import one of the 3 SDKs (expect exactly the 3 provider client files) --"
docker compose exec -T backend grep -rlE "^\s*(import|from)\s+(anthropic|openai(\.| |\$)|google\.genai|from google import genai)" app/
echo "-- violations (expect NO output) --"
if docker compose exec -T backend sh -c "grep -rlE '^\s*(import|from)\s+(anthropic|openai(\.| |\$)|google\.genai|from google import genai)' app/ | grep -v '^app/ai_gateway/providers/'"; then
  echo "FAILED: a file outside app/ai_gateway/providers/ imports a provider SDK directly - this violates the approved boundary"
  exit 1
else
  echo "confirmed: only app/ai_gateway/providers/*.py import a provider SDK directly"
fi

echo
echo "=== 4/7: layering boundary - no upward dependency between the new packages, and workflow_engine still has zero reference to any of them ==="
docker compose exec -T backend sh -c "
set -e
! grep -rlE 'ai_gateway|ai_agents|prompt_builder' app/workflow_engine/ app/workflow_actions/ 2>/dev/null | grep -q . \
  && echo 'confirmed: app/workflow_engine/ and app/workflow_actions/ have zero reference to the new M7.2 packages (no wiring done this milestone, as scoped)' \
  || (echo 'FAILED: workflow_engine/workflow_actions already reference an M7.2 package - out of scope for this milestone' && exit 1)
! grep -rlE 'from app\.ai_agents|from app\.prompt_builder|import app\.ai_agents|import app\.prompt_builder' app/ai_gateway/ 2>/dev/null | grep -q . \
  && echo 'confirmed: app/ai_gateway/ never imports app.ai_agents or app.prompt_builder (no upward dependency)' \
  || (echo 'FAILED: app/ai_gateway/ has an upward dependency on a layer above it' && exit 1)
! grep -rlE 'from app\.ai_agents|import app\.ai_agents' app/prompt_builder/ 2>/dev/null | grep -q . \
  && echo 'confirmed: app/prompt_builder/ never imports app.ai_agents (no upward dependency)' \
  || (echo 'FAILED: app/prompt_builder/ has an upward dependency on app.ai_agents' && exit 1)
"

echo
echo "=== 5/7: the real, sandbox-and-container-executable AI Execution Platform test suite ==="
echo "-- Agent Runtime -> Prompt Builder -> AI Gateway -> Provider Router -> FakeProviderClient -> Agent.interpret, exercised end to end with local test doubles (no live API call, no database) --"
docker compose exec -T backend python -m unittest tests.test_ai_execution_platform_e2e -v

echo
echo "=== 6/7: full regression - M7.1 workflow engine + pilot workflow suites still green (M7.2 touched nothing under app/workflow_engine/ or app/workflow_actions/, but re-run for completeness) ==="
docker compose exec -T backend python -m unittest tests.test_action_registry tests.test_workflow_definition_validation tests.test_workflow_events tests.test_workflow_definitions tests.test_workflow_instance_models tests.test_event_dispatcher_worker tests.test_step_runner_worker tests.test_pilot_workflow_e2e -v

echo
echo "=== 7/7: SQLAlchemy mapper configuration (M7.2 added zero models/migrations, so this should be an unaffected no-op check) ==="
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
echo "  - No live call to a real Claude/OpenAI/Gemini API has been made anywhere in this project. Every"
echo "    ProviderClient's error-mapping logic (which real SDK exception maps to which GatewayError subclass) is"
echo "    based on each SDK's documented behavior, not a verified live failure. Gemini's client carries the most"
echo "    honest uncertainty here - see gemini_client.py's own docstring."
echo "  - AI_GATEWAY_DEFAULT_TIMEOUT_SECONDS/AI_GATEWAY_MAX_ATTEMPTS_PER_PROVIDER's real-world tuning is unverified -"
echo "    no live call means no real latency/failure-rate data exists yet to validate these defaults against."
echo "  - Zero Workflow Actions invoke AgentRuntime yet, and zero WorkflowDefinitions reference an AI-backed step -"
echo "    wiring a real Agent into a real workflow is explicitly out of scope for M7.2 (future M7.3+ work)."
echo "  - Hard budget enforcement (BudgetExceededError) is not implemented - GatewayRequest.budget_usd is checked"
echo "    softly (logged, not enforced) - see app/ai_gateway/client.py's own docstring for why."
echo "  - PROMPT_REGISTRY (app/ai_agents/prompts/registry.py) ships with zero registered templates - there is no"
echo "    real Agent yet to populate it. Only the mechanism was built this milestone."
