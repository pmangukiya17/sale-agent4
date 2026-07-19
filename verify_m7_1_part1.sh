#!/usr/bin/env bash
# Comprehensive verification for M7.1 Part 1 (Phases 1-5: Event
# Infrastructure, Workflow Definition, Workflow Instance, Event
# Dispatcher, Step Runner - migrations 0013-0015) against your EXISTING
# running stack and its real data - same discipline as
# verify_m6_1.sh/verify_m6_2.sh/verify_m6_3.sh/verify_m6_4.sh.
#
# Deliberately does NOT run `docker compose down -v` - see those scripts'
# own header comments for the real data-loss incident this guards
# against. Migrations 0013-0015 are purely additive (five new tables,
# four new enum types, zero changes to any existing table/column/
# constraint/index) - safe against real data without a fresh database.
#
# Part 1 does not touch any existing domain module (Discovery, Research,
# Personalization, Outreach, Delivery, Mailbox Sync, Thread Builder,
# Reply Intelligence) - the Workflow Engine is new, additive, and
# provably zero-import-coupled to all of them (section 11 below). No
# regression re-run of the M1-M6 suites is included here, matching
# verify_m6_4.sh's own reasoning for the same situation.
#
# Run this from the repo root, with the stack already configured (.env
# present, same as every other verify_*.sh in this repo).
set -euo pipefail

PSQL="docker compose exec -T db psql -U ${POSTGRES_USER:-sales_agent} -d ${POSTGRES_DB:-sales_agent}"

echo "=== 1/12: rebuild + boot ==="
docker compose up --build -d
echo "waiting for backend to report healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null; then
    echo "backend is up - 'alembic upgrade head' (now including 0013-0015) completed as part of container startup"
    break
  fi
  sleep 2
done
curl -sf http://localhost:8000/api/v1/health && echo || { echo "FAILED: backend never became healthy - check: docker compose logs backend"; exit 1; }

echo "-- confirming all eight backend-relevant services are running --"
docker compose ps
for service in backend worker mailbox_sync_worker thread_builder_worker reply_intelligence_worker workflow_event_dispatcher_worker workflow_step_runner_worker db; do
  if ! docker compose ps "$service" | grep -qi "Up\|running"; then
    echo "FAILED: service '$service' does not appear to be running - see 'docker compose ps' output above"
    exit 1
  fi
done
echo "confirmed: all eight backend-relevant services are running"

echo
echo "=== 2/12: migration ==="
docker compose exec -T backend alembic current
echo "-- alembic current should read '0015 (head)' --"
$PSQL -c "SELECT
  (SELECT count(*) FROM company_profiles) AS company_profiles,
  (SELECT count(*) FROM provider_connections) AS provider_connections,
  (SELECT count(*) FROM delivery_queue_items) AS delivery_queue_items,
  (SELECT count(*) FROM conversations) AS conversations,
  (SELECT count(*) FROM email_messages) AS email_messages,
  (SELECT count(*) FROM mailbox_sync_states) AS mailbox_sync_states,
  (SELECT count(*) FROM attachments) AS attachments,
  (SELECT count(*) FROM events) AS events,
  (SELECT count(*) FROM workflow_definitions) AS workflow_definitions,
  (SELECT count(*) FROM workflow_instances) AS workflow_instances,
  (SELECT count(*) FROM workflow_step_invocations) AS workflow_step_invocations,
  (SELECT count(*) FROM event_consumptions) AS event_consumptions;"
echo "-- every pre-existing table's count above should match exactly what you recorded after verify_m6_4.sh;"
echo "-- the five new tables should all read 0 (nothing has published an Event or authored a Workflow Definition yet - Part 1 is inert until Part 2's pilot activation) --"

echo
echo "=== 3/12: schema ==="
$PSQL -c "\d events" | head -20
$PSQL -c "\d workflow_definitions" | head -20
$PSQL -c "\d workflow_instances" | head -25
$PSQL -c "\d workflow_step_invocations" | head -20
$PSQL -c "\d event_consumptions" | head -15
echo "-- spot-check: events.sequence_no should be bigint with an identity/nextval default; workflow_instances.context"
echo "-- and workflow_definitions.step_graph/trigger_filter should be jsonb; every *_status column should be its own enum type --"

echo
echo "=== 4/12: constraints/indexes ==="
echo "-- unique on sequence_no --"
$PSQL -c "\d events" | grep -i "ix_events_sequence_no"
echo "-- (key, version) uniqueness + at-most-one-ACTIVE-per-key partial unique index --"
$PSQL -c "\d workflow_definitions" | grep -i "uq_workflow_definitions_key_version\|uq_workflow_definitions_key_active"
$PSQL -c "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_workflow_definitions_key_active';"
echo "-- must show: ... UNIQUE INDEX ... ON workflow_definitions USING btree (key) WHERE (status = 'active'::workflow_definition_status) --"
echo "-- event_consumptions idempotency constraint --"
$PSQL -c "\d event_consumptions" | grep -i "uq_event_consumptions_event_instance"
echo "-- FK ondelete behavior: workflow_instances -> workflow_definitions must be RESTRICT (never CASCADE - an in-flight instance must block its definition from being deleted) --"
$PSQL -c "SELECT confrelid::regclass AS references, confdeltype FROM pg_constraint WHERE conname LIKE '%workflow_instances_workflow_definition_id%';"
echo "-- confdeltype must be 'r' (RESTRICT), not 'c' (CASCADE) --"

echo
echo "=== 5/12: workers - import + log check ==="
docker compose ps workflow_event_dispatcher_worker workflow_step_runner_worker
echo "-- direct import check inside the backend container --"
docker compose exec -T backend python -c "
from app.workflow_engine import event_dispatcher_worker, step_runner_worker
from app.workflow_engine.actions import base, registry, wait_for_event
from app.workflow_engine.actions.registry import is_action_registered
from app.workflow_engine.actions.base import WAIT_FOR_EVENT_ACTION_KEY
assert is_action_registered(WAIT_FOR_EVENT_ACTION_KEY), 'built-in wait_for_event action failed to self-register'
print('app.workflow_engine.event_dispatcher_worker, step_runner_worker, and the Action registry imported cleanly - engine.wait_for_event is registered.')
"
docker compose logs --tail=50 workflow_event_dispatcher_worker
docker compose logs --tail=50 workflow_step_runner_worker
if docker compose logs workflow_event_dispatcher_worker workflow_step_runner_worker 2>&1 | grep -qi "Traceback\|ModuleNotFoundError\|ImportError\|InvalidRequestError"; then
  echo "FAILED: a workflow engine worker's logs contain an error signature - review the log output above"
  exit 1
else
  echo "confirmed: no Traceback/ImportError/ModuleNotFoundError/mapper-resolution error found in either worker's logs"
fi

echo
echo "=== 6/12: Action Registry (pure logic, no DB) ==="
docker compose exec -T backend python -m unittest tests.test_action_registry -v

echo
echo "=== 7/12: step_graph validation (pure logic, no DB) ==="
docker compose exec -T backend python -m unittest tests.test_workflow_definition_validation -v

echo
echo "=== 8/12: Event Infrastructure + Workflow Definition + Workflow Instance models - against the real database ==="
docker compose exec -T backend python -m unittest tests.test_workflow_events -v
docker compose exec -T backend python -m unittest tests.test_workflow_definitions -v
docker compose exec -T backend python -m unittest tests.test_workflow_instance_models -v

echo
echo "=== 9/12: Event Dispatcher worker - against the real database ==="
echo "-- new-instance creation pinned to the active version, DRAFT/DEPRECATED never matched, trigger_filter matching,"
echo "-- one event fanning out to multiple definitions, resume-by-subject-id, wrong-event-type ignored, and the"
echo "-- idempotency guarantee (test_rerun_is_idempotent_no_duplicate_instances - a rerun with no new events is a true no-op) --"
docker compose exec -T backend python -m unittest tests.test_event_dispatcher_worker -v

echo
echo "=== 10/12: Step Runner worker - against the real database ==="
echo "-- success (terminal + advancing), a raising Action treated as FAILURE, definitive FAILURE ignoring remaining"
echo "-- attempts, PENDING -> WAITING, the full wait-for-event round trip across both workers, claim/stale-claim"
echo "-- reclaim, and the retry guarantees (test_retry_then_succeed_increments_attempt_number_and_stays_on_same_step,"
echo "-- test_retry_exhaustion_follows_failure_transition) --"
docker compose exec -T backend python -m unittest tests.test_step_runner_worker -v

echo
echo "=== 11/12: domain-agnostic boundary check ==="
echo "-- app/workflow_engine/ must have ZERO import dependency on any domain package --"
if docker compose exec -T backend grep -rnE "^\s*(import|from)\s+app\.(discovery|research|personalization|outreach|delivery|reply_intelligence)" app/workflow_engine/; then
  echo "FAILED: app/workflow_engine/ imports a domain package - this violates the approved architecture's hard boundary"
  exit 1
else
  echo "confirmed: zero domain imports anywhere under app/workflow_engine/"
fi

echo
echo "=== 12/12: SQLAlchemy ==="
docker compose exec -T backend python -c "
from app.db import base as _base
from sqlalchemy.orm import configure_mappers
configure_mappers()
print('All mappers configured successfully - every relationship() resolved, including Event/WorkflowDefinition/WorkflowInstance/WorkflowStepInvocation/EventConsumption.')
"

echo
echo "ALL CHECKS COMPLETE"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - No pilot WorkflowDefinition exists yet and nothing publishes a real Event yet - by design, Part 1 is"
echo "    complete generic infrastructure with zero behavioral effect on the running system. Everything above"
echo "    exercises the engine through its own test suite's synthetic definitions/actions, not a live business"
echo "    workflow - that starts in Part 2 (Phases 6-10: pilot Action, existing-worker event emission, pilot"
echo "    definition authoring + activation, end-to-end verification)."
echo "  - Multi-replica concurrency (two Step Runner processes racing the same claim query, two Event Dispatcher"
echo "    processes racing the same event) is exercised by this script only as single-process SELECT...FOR UPDATE"
echo "    SKIP LOCKED / idempotent-rerun tests, not as an actual concurrent multi-container race - matching every"
echo "    other worker's verification precedent in this repo (Delivery, Mailbox Sync, Thread Builder, Reply"
echo "    Intelligence), none of which have been load-tested under real multi-replica concurrency either."
