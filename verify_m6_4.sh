#!/usr/bin/env bash
# Comprehensive verification for M6.4 (Reply Intelligence, migration
# 0012) against your EXISTING running stack and its real data - same
# discipline as verify_m6_1.sh/verify_m6_2.sh/verify_m6_3.sh.
#
# Deliberately does NOT run `docker compose down -v` - see those scripts'
# own header comments for the real data-loss incident this guards
# against. Migration 0012 is purely additive (four new nullable/
# default-false columns, one new enum type, three new indexes) - safe
# against real data without a fresh database.
#
# M6.4 does not touch any M6.1/M6.2/M6.3 file except enums.py and
# conversation.py (additive only) - no full regression re-run of the
# M6.1-M6.3 suites is included here, unlike verify_m6_3.sh's section 9
# (which existed because M6.3 touched shared provider/model files this
# milestone does not).
set -euo pipefail

PSQL="docker compose exec -T db psql -U ${POSTGRES_USER:-sales_agent} -d ${POSTGRES_DB:-sales_agent}"

echo "=== 1/9: rebuild + boot ==="
docker compose up --build -d
echo "waiting for backend to report healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null; then
    echo "backend is up - 'alembic upgrade head' (now including 0012) completed as part of container startup"
    break
  fi
  sleep 2
done
curl -sf http://localhost:8000/api/v1/health && echo || { echo "FAILED: backend never became healthy - check: docker compose logs backend"; exit 1; }

echo "-- confirming all six services are running (backend, worker, mailbox_sync_worker, thread_builder_worker, reply_intelligence_worker, db) --"
docker compose ps
for service in backend worker mailbox_sync_worker thread_builder_worker reply_intelligence_worker db; do
  if ! docker compose ps "$service" | grep -qi "Up\|running"; then
    echo "FAILED: service '$service' does not appear to be running - see 'docker compose ps' output above"
    exit 1
  fi
done
echo "confirmed: all six services are running"

echo
echo "=== 2/9: migration ==="
docker compose exec -T backend alembic current
echo "-- alembic current should read '0012 (head)' --"
$PSQL -c "SELECT
  (SELECT count(*) FROM company_profiles) AS company_profiles,
  (SELECT count(*) FROM provider_connections) AS provider_connections,
  (SELECT count(*) FROM delivery_queue_items) AS delivery_queue_items,
  (SELECT count(*) FROM conversations) AS conversations,
  (SELECT count(*) FROM email_messages) AS email_messages,
  (SELECT count(*) FROM mailbox_sync_states) AS mailbox_sync_states,
  (SELECT count(*) FROM attachments) AS attachments;"
echo "-- compare against what you recorded after verify_m6_3.sh - every number above should match exactly --"

echo
echo "=== 3/9: schema ==="
$PSQL -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'conversations' AND column_name IN ('reply_status','last_reply_at','last_reply_from','needs_human_review') ORDER BY column_name;"
echo "-- all four columns above must exist: reply_status (USER-DEFINED/enum), last_reply_at (timestamptz), last_reply_from (varchar), needs_human_review (boolean) --"
$PSQL -c "SELECT enumlabel FROM pg_enum WHERE enumtypid = 'reply_status'::regtype ORDER BY enumsortorder;"
echo "-- must be exactly: positive, negative, neutral, out_of_office --"

echo
echo "=== 4/9: constraints/indexes ==="
$PSQL -c "\d conversations" | grep -i "ix_conversations_reply_status\|ix_conversations_last_reply_at\|ix_conversations_needs_human_review"
echo "-- regression check: the M6.1 conversation_status index must still exist, untouched --"
$PSQL -c "\d conversations" | grep -i "ix_conversations_status\|conversations_status"

echo
echo "=== 5/9: worker ==="
docker compose ps reply_intelligence_worker
echo "-- direct import check inside the backend container --"
docker compose exec -T backend python -c "
from app.reply_intelligence import reply_intelligence_worker
from app.reply_intelligence.classifiers import base, rules_classifier, registry
from app.core.text_extraction import extract_plain_text
print('app.reply_intelligence.reply_intelligence_worker and its dependencies imported cleanly - no import errors.')
"
docker compose logs --tail=50 reply_intelligence_worker
if docker compose logs reply_intelligence_worker 2>&1 | grep -qi "Traceback\|ModuleNotFoundError\|ImportError\|InvalidRequestError"; then
  echo "FAILED: reply_intelligence_worker logs contain an error signature - review the log output above"
  exit 1
else
  echo "confirmed: no Traceback/ImportError/ModuleNotFoundError/mapper-resolution error found in reply_intelligence_worker logs"
fi

echo
echo "=== 6/9: shared text extraction (pure logic, no DB) ==="
docker compose exec -T backend python -m unittest tests.test_text_extraction -v

echo
echo "=== 7/9: deterministic rules classifier (pure logic, no DB) ==="
docker compose exec -T backend python -m unittest tests.test_rules_classifier -v

echo
echo "=== 8/9: Reply Intelligence worker - orchestration against the real database ==="
echo "-- classification + field writes, negative -> needs_human_review, HTML-only body via shared "
echo "-- text extraction, ignores outbound-only conversations, ignores never-threaded messages, "
echo "-- idempotent rerun, latest-reply-wins, reclassifies when a newer reply arrives --"
docker compose exec -T backend python -m unittest tests.test_reply_intelligence_worker -v

echo
echo "=== 9/9: SQLAlchemy ==="
docker compose exec -T backend python -c "
from app.db import base as _base
from sqlalchemy.orm import configure_mappers
configure_mappers()
print('All mappers configured successfully - every relationship() resolved.')
"

echo
echo "ALL CHECKS COMPLETE"
echo
echo "NOT covered by anything above - a disclosed, deferred concern:"
echo "  - Real end-to-end reply classification (an actual inbound reply, correctly threaded by"
echo "    Thread Builder, then correctly classified by this worker) still depends on the same"
echo "    Mail.Read/Reconnect-scope gap disclosed in verify_m6_2.sh/verify_m6_3.sh - unchanged by"
echo "    M6.4. Everything above is real database-backed and provider-independent (deterministic"
echo "    rules only, no external AI call), but a live inbound reply has not been observed by this"
echo "    pipeline end-to-end yet."
