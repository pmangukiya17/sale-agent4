#!/usr/bin/env bash
# Comprehensive verification for M6.2 (MailboxSyncState/Attachment schema,
# migration 0010, the mailbox sync worker, and OutlookProvider's
# IncrementalSyncCapable implementation) against your EXISTING running
# stack and its real data - same 10-section structure requested, mirroring
# verify_m6_1.sh's discipline.
#
# Deliberately does NOT run `docker compose down -v` - same reasoning as
# verify_m6_1.sh: that command wipes the entire named Postgres volume and
# is exactly what caused the real data-loss incident investigated earlier
# in this project. Migration 0010 is additive (two new tables, one new
# enum type) plus ONE alter (email_messages.conversation_id -> nullable) -
# the alter only WIDENS what's allowed (a NOT NULL column becoming
# nullable can never reject a pre-existing row, since every existing row
# already satisfies NOT NULL), so it is safe to apply to your real data
# without a fresh database.
#
# A downgrade/re-upgrade check is intentionally NOT included as a
# numbered step here (unlike verify_m6_1.sh) - downgrading migration 0010
# requires every email_messages row to already have a non-NULL
# conversation_id, which will not be true once the sync worker has
# written anything (expected and correct - see migration 0010's own
# downgrade() docstring). Run `docker compose exec -T backend alembic
# downgrade -1` manually only if you want to test that path before any
# real sync data exists.
set -euo pipefail

PSQL="docker compose exec -T db psql -U ${POSTGRES_USER:-sales_agent} -d ${POSTGRES_DB:-sales_agent}"

echo "=== 1/10: rebuild + boot ==="
docker compose up --build -d
echo "waiting for backend to report healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null; then
    echo "backend is up - 'alembic upgrade head' (now including 0010) completed as part of container startup"
    break
  fi
  sleep 2
done
curl -sf http://localhost:8000/api/v1/health && echo || { echo "FAILED: backend never became healthy - check: docker compose logs backend"; exit 1; }

echo "-- confirming all four services are running (backend, worker, mailbox_sync_worker, db) --"
docker compose ps
echo "-- each of backend/worker/mailbox_sync_worker/db above should show state 'Up' (or 'running') --"
for service in backend worker mailbox_sync_worker db; do
  if ! docker compose ps "$service" | grep -qi "Up\|running"; then
    echo "FAILED: service '$service' does not appear to be running - see 'docker compose ps' output above"
    exit 1
  fi
done
echo "confirmed: backend, worker, mailbox_sync_worker, and db are all running"

echo
echo "=== 2/10: migration ==="
docker compose exec -T backend alembic current
echo "-- alembic current should read '0010 (head)' --"
echo "-- existing M0-M6.1 row counts, unchanged by this migration --"
$PSQL -c "SELECT
  (SELECT count(*) FROM company_profiles) AS company_profiles,
  (SELECT count(*) FROM prospects) AS prospects,
  (SELECT count(*) FROM provider_connections) AS provider_connections,
  (SELECT count(*) FROM delivery_queue_items) AS delivery_queue_items,
  (SELECT count(*) FROM conversations) AS conversations,
  (SELECT count(*) FROM email_messages) AS email_messages,
  (SELECT count(*) FROM conversation_participants) AS conversation_participants;"
echo "-- compare against what you recorded after verify_m6_1.sh - every number above should match exactly --"

echo
echo "=== 3/10: schema ==="
$PSQL -c "\dt" | grep -E "mailbox_sync_states|attachments"
echo "-- both tables above must exist --"
$PSQL -c "SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name = 'email_messages' AND column_name = 'conversation_id';"
echo "-- is_nullable must read YES --"

echo
echo "=== 4/10: constraints ==="
echo "-- foreign keys on the two new tables --"
$PSQL -c "
SELECT tc.table_name, kcu.column_name, ccu.table_name AS references_table, rc.delete_rule
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_name IN ('mailbox_sync_states','attachments')
ORDER BY tc.table_name, kcu.column_name;
"
echo "-- expect: attachments.email_message_id -> email_messages, delete_rule=CASCADE --"
echo "-- expect: mailbox_sync_states.provider_connection_id -> provider_connections, delete_rule=RESTRICT --"
echo "-- unique constraint on mailbox_sync_states.provider_connection_id --"
$PSQL -c "\d mailbox_sync_states" | grep -i "uq_mailbox_sync_states_provider_connection_id"
echo "-- the M6.1 dedup index must still exist, untouched by migration 0010 --"
$PSQL -c "\d email_messages" | grep -i "uq_email_messages_connection_internet_message_id"

echo
echo "=== 5/10: worker ==="
echo "-- mailbox_sync_worker container state --"
docker compose ps mailbox_sync_worker
echo "-- direct import check inside the backend container - proves no ImportError/ModuleNotFoundError --"
docker compose exec -T backend python -c "
from app.reply_intelligence import sync_worker, normalize
print('app.reply_intelligence.sync_worker and .normalize imported cleanly - no import errors.')
"
echo "-- mailbox_sync_worker's own recent logs - look for a clean startup line and the absence of any Traceback --"
docker compose logs --tail=50 mailbox_sync_worker
if docker compose logs mailbox_sync_worker 2>&1 | grep -qi "Traceback\|ModuleNotFoundError\|ImportError\|InvalidRequestError"; then
  echo "FAILED: mailbox_sync_worker logs contain an error signature - review the log output above"
  exit 1
else
  echo "confirmed: no Traceback/ImportError/ModuleNotFoundError/mapper-resolution error found in mailbox_sync_worker logs"
fi

echo
echo "=== 6/10: normalization ==="
echo "-- pure logic, no DB - normalize.py's RawEmailMessage/RawAttachment -> ORM-kwargs mapping --"
docker compose exec -T backend python -m unittest tests.test_reply_intelligence_normalize -v

echo
echo "=== 7/10: database tests ==="
echo "-- real-DB schema/constraint tests: MailboxSyncState uniqueness, Attachment cascade, "
echo "-- conversation_id NULL persistence, and the M6.1 dedup index re-verified post-migration --"
docker compose exec -T backend python -m unittest tests.test_mailbox_sync_models -v

echo
echo "=== 8/10: cursor contract ==="
echo "-- real-DB, stub-provider tests of sync_worker.sync_one_connection's own orchestration: "
echo "-- initial sync, cursor advances only after messages commit, in-tick duplicate skip, "
echo "-- rerun idempotency, and failure/recovery behavior --"
docker compose exec -T backend python -m unittest tests.test_sync_worker_cursor_contract -v

echo
echo "=== 9/10: Outlook adapter ==="
echo "-- OutlookProvider.fetch_messages_incremental() against MOCKED Graph HTTP responses - "
echo "-- no live Graph credentials, no network call --"
docker compose exec -T backend python -m unittest tests.test_outlook_provider_sync -v

echo
echo "=== 10/10: SQLAlchemy ==="
docker compose exec -T backend python -c "
from app.db import base as _base
from sqlalchemy.orm import configure_mappers
configure_mappers()
print('All mappers configured successfully - every relationship() resolved.')
"

echo
echo "ALL CHECKS COMPLETE"
echo
echo "NOTE (disclosed gap, not a failure of anything above): the mailbox sync"
echo "worker's per-tick loop will report 0 eligible connections in your real"
echo "environment until at least one ProviderConnection has been granted"
echo "Mail.Read - M6.2's approved scope did not include a Reconnect-with-"
echo "expanded-scopes route. Sections 1-10 above verify the schema, the"
echo "worker's orchestration logic, and the Outlook adapter's parsing logic"
echo "independently of that gap (via the stub-provider and mocked-Graph"
echo "tests in sections 8-9), so a real end-to-end sync against a live"
echo "mailbox is the one thing this script cannot exercise without that"
echo "follow-up (or a manually re-scoped connection for testing)."
