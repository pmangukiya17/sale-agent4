#!/usr/bin/env bash
# Comprehensive verification for M7.1 Part 2 (the pilot workflow:
# conversation.created -> workflow.record_execution -> COMPLETED)
# against your EXISTING running stack and its real data - same
# discipline as verify_m7_1_part1.sh and every verify_m6_*.sh before it.
#
# Deliberately does NOT run `docker compose down -v` - see those
# scripts' own header comments for the real data-loss incident this
# guards against. Part 2 adds no new tables/migrations (the pilot
# WorkflowDefinition is DATA, authored through the existing governed
# lifecycle on backend startup, not a schema change) - safe against real
# data without a fresh database.
#
# Run this AFTER verify_m7_1_part1.sh has come back fully green. This
# script assumes Part 1's tables/workers already exist and pass.
set -euo pipefail

PSQL="docker compose exec -T db psql -U ${POSTGRES_USER:-sales_agent} -d ${POSTGRES_DB:-sales_agent}"

echo "=== 1/8: rebuild + boot ==="
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

echo "-- confirming every backend-relevant service is running, including the RENAMED step runner command --"
docker compose ps
for service in backend worker mailbox_sync_worker thread_builder_worker reply_intelligence_worker workflow_event_dispatcher_worker workflow_step_runner_worker db; do
  if ! docker compose ps "$service" | grep -qi "Up\|running"; then
    echo "FAILED: service '$service' does not appear to be running - see 'docker compose ps' output above"
    exit 1
  fi
done
echo "confirmed: all backend-relevant services are running"

echo
echo "=== 2/8: built-in workflow bootstrap ran on backend startup ==="
docker compose logs backend | grep -i "conversation_created_pilot" || { echo "FAILED: backend logs contain no mention of the pilot workflow bootstrap"; exit 1; }
echo "-- above should show either 'Activated built-in workflow' (first boot) or 'already ACTIVE ... skipping' (subsequent boots) --"
$PSQL -c "SELECT key, version, status, trigger_event_type FROM workflow_definitions WHERE key = 'conversation_created_pilot';"
echo "-- must show exactly one row: version 1, status active, trigger_event_type conversation.created --"

echo
echo "=== 3/8: step runner worker boots via the new composition-root entrypoint ==="
docker compose logs workflow_step_runner_worker | tail -20
if docker compose logs workflow_step_runner_worker 2>&1 | grep -qi "Traceback\|ModuleNotFoundError\|ImportError\|InvalidRequestError"; then
  echo "FAILED: workflow_step_runner_worker logs contain an error signature - review the log output above"
  exit 1
fi
echo "-- direct import check inside the backend container: app.run_step_runner_worker must import cleanly and register the pilot action --"
docker compose exec -T backend python -c "
import app.run_step_runner_worker  # noqa: F401 - importing this module itself triggers app.workflow_actions' registration
from app.workflow_engine.actions.registry import is_action_registered
from app.workflow_actions.record_execution_action import RECORD_EXECUTION_ACTION_KEY
assert is_action_registered(RECORD_EXECUTION_ACTION_KEY), 'pilot action failed to register via app.run_step_runner_worker'
print('app.run_step_runner_worker imports cleanly and workflow.record_execution is registered.')
"
echo "-- structural check: app/workflow_engine/ itself must NEVER import app.workflow_actions or app.workflow_bootstrap --"
if docker compose exec -T backend grep -rnE "^\s*(import|from)\s+app\.(workflow_actions|workflow_bootstrap)" app/workflow_engine/; then
  echo "FAILED: app/workflow_engine/ imports a concrete Action-providing package - this violates the approved boundary"
  exit 1
else
  echo "confirmed: app/workflow_engine/ has zero import dependency on app.workflow_actions/app.workflow_bootstrap"
fi

echo
echo "=== 4/8: domain-agnostic boundary check (unchanged from Part 1, re-run for completeness) ==="
if docker compose exec -T backend grep -rnE "^\s*(import|from)\s+app\.(discovery|research|personalization|outreach|delivery|reply_intelligence)" app/workflow_engine/; then
  echo "FAILED: app/workflow_engine/ imports a domain package"
  exit 1
else
  echo "confirmed: zero domain imports anywhere under app/workflow_engine/"
fi

echo
echo "=== 5/8: the reference end-to-end test - Conversation created -> publish_event -> Event stored -> Event Dispatcher -> WorkflowInstance created -> Step Runner -> pilot Action executed -> Workflow completed ==="
docker compose exec -T backend python -m unittest tests.test_pilot_workflow_e2e -v

echo
echo "=== 6/8: M6.3 Thread Builder regression - conversation.created wiring must not change existing threading behavior ==="
docker compose exec -T backend python -m unittest tests.test_thread_builder -v

echo
echo "=== 7/8: Part 1 regression - full workflow engine suite still green ==="
docker compose exec -T backend python -m unittest tests.test_action_registry tests.test_workflow_definition_validation tests.test_workflow_events tests.test_workflow_definitions tests.test_workflow_instance_models tests.test_event_dispatcher_worker tests.test_step_runner_worker -v

echo
echo "=== 8/8: SQLAlchemy ==="
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
echo "  - Only ONE production trigger (conversation.created, from the inbound-unmatched branch of thread_builder.py)"
echo "    is wired. The outbound path (dispatch_service.py's get_or_create_conversation_for_outbound) remains an"
echo "    explicitly deferred, documented future hook point, per the approved Part 2 scope."
echo "  - The pilot Action (workflow.record_execution) always returns SUCCESS - there is no real failure path to"
echo "    observe yet (by design: Part 2 validates the engine, not business functionality). Retry/failure-transition"
echo "    behavior against a REAL (non-synthetic) Action is still only proven by Part 1's own synthetic-action tests."
echo "  - activate_builtin_workflows() is additive-only: if BUILTIN_WORKFLOW_DEFINITIONS' step_graph for a key ever"
echo "    changes in code, this bootstrap will NOT auto-publish a new version of an already-ACTIVE built-in - that"
echo "    remains a deliberate, separate, not-yet-built authoring operation (see workflow_bootstrap.py's own"
echo "    docstring)."
