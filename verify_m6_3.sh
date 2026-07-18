#!/usr/bin/env bash
# Comprehensive verification for M6.3 (Thread Builder, outbound
# correlation, migration 0011) against your EXISTING running stack and
# its real data - same discipline as verify_m6_1.sh/verify_m6_2.sh.
#
# Deliberately does NOT run `docker compose down -v` - see those two
# scripts' own header comments for the real data-loss incident this
# guards against. Migration 0011 is purely additive (two new nullable
# columns, one new plain index) - safe against real data without a fresh
# database.
#
# M6.3 touched shared M6.1/M6.2 files (email_message.py, base.py,
# outlook_provider.py, normalize.py) - so this script re-runs the FULL
# M6.1/M6.2 test suite too (section 9), not just the new M6.3 tests, as a
# real regression check, not an assumption that "additive" changes didn't
# break anything.
set -euo pipefail

PSQL="docker compose exec -T db psql -U ${POSTGRES_USER:-sales_agent} -d ${POSTGRES_DB:-sales_agent}"

echo "=== 1/10: rebuild + boot ==="
docker compose up --build -d
echo "waiting for backend to report healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null; then
    echo "backend is up - 'alembic upgrade head' (now including 0011) completed as part of container startup"
    break
  fi
  sleep 2
done
curl -sf http://localhost:8000/api/v1/health && echo || { echo "FAILED: backend never became healthy - check: docker compose logs backend"; exit 1; }

echo "-- confirming all five services are running (backend, worker, mailbox_sync_worker, thread_builder_worker, db) --"
docker compose ps
for service in backend worker mailbox_sync_worker thread_builder_worker db; do
  if ! docker compose ps "$service" | grep -qi "Up\|running"; then
    echo "FAILED: service '$service' does not appear to be running - see 'docker compose ps' output above"
    exit 1
  fi
done
echo "confirmed: all five services are running"

echo
echo "=== 2/10: migration ==="
docker compose exec -T backend alembic current
echo "-- alembic current should read '0011 (head)' --"
$PSQL -c "SELECT
  (SELECT count(*) FROM company_profiles) AS company_profiles,
  (SELECT count(*) FROM provider_connections) AS provider_connections,
  (SELECT count(*) FROM delivery_queue_items) AS delivery_queue_items,
  (SELECT count(*) FROM conversations) AS conversations,
  (SELECT count(*) FROM email_messages) AS email_messages,
  (SELECT count(*) FROM mailbox_sync_states) AS mailbox_sync_states,
  (SELECT count(*) FROM attachments) AS attachments;"
echo "-- compare against what you recorded after verify_m6_2.sh - every number above should match exactly --"

echo
echo "=== 3/10: schema ==="
$PSQL -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'email_messages' AND column_name IN ('to_recipients','cc_recipients') ORDER BY column_name;"
echo "-- both columns above must exist, data_type jsonb --"

echo
echo "=== 4/10: constraints ==="
echo "-- the new non-unique index on internet_message_id --"
$PSQL -c "\d email_messages" | grep -i "ix_email_messages_internet_message_id"
echo "-- regression check: the M6.1 partial unique dedup index must still exist, untouched --"
$PSQL -c "\d email_messages" | grep -i "uq_email_messages_connection_internet_message_id"
echo "-- regression check: the M6.2 MailboxSyncState unique constraint must still exist, untouched --"
$PSQL -c "\d mailbox_sync_states" | grep -i "uq_mailbox_sync_states_provider_connection_id"

echo
echo "=== 5/10: worker ==="
docker compose ps thread_builder_worker
echo "-- direct import check inside the backend container --"
docker compose exec -T backend python -c "
from app.reply_intelligence import thread_builder, thread_matching, conversation_resolver, subject_normalize
print('app.reply_intelligence.thread_builder and its dependencies imported cleanly - no import errors.')
"
docker compose logs --tail=50 thread_builder_worker
if docker compose logs thread_builder_worker 2>&1 | grep -qi "Traceback\|ModuleNotFoundError\|ImportError\|InvalidRequestError"; then
  echo "FAILED: thread_builder_worker logs contain an error signature - review the log output above"
  exit 1
else
  echo "confirmed: no Traceback/ImportError/ModuleNotFoundError/mapper-resolution error found in thread_builder_worker logs"
fi

echo
echo "=== 6/10: subject normalization (pure logic, no DB) ==="
docker compose exec -T backend python -m unittest tests.test_subject_normalize -v

echo
echo "=== 7/10: conversation resolver (outbound Conversation/Participant logic) ==="
docker compose exec -T backend python -m unittest tests.test_conversation_resolver -v

echo
echo "=== 8/10: Thread Builder - the full M6.3 threading algorithm ==="
echo "-- new conversation creation, existing-conversation matching (thread id / In-Reply-To / References), "
echo "-- reply correlation, duplicate handling, out-of-order arrival, missing headers, multi-participant "
echo "-- conversations, provider-independent behavior, the Message-ID-wins conflict rule, and the "
echo "-- strengthened subject-fallback conditions (OPEN-only, participant overlap required) --"
docker compose exec -T backend python -m unittest tests.test_thread_builder -v

echo
echo "=== 9/10: full M6.1/M6.2 regression - M6.3 touched shared provider/model files ==="
docker compose exec -T backend python -m unittest tests.test_conversation_models -v
docker compose exec -T backend python -m unittest tests.test_mailbox_sync_models -v
docker compose exec -T backend python -m unittest tests.test_reply_intelligence_normalize -v
docker compose exec -T backend python -m unittest tests.test_sync_worker_cursor_contract -v
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
echo "NOT covered by anything above, and still requiring a real, manual send:"
echo "  - OutlookProvider.send() now does create-draft-then-send (two Graph calls instead of"
echo "    one) - this is UNVERIFIED BY EXECUTION, same disclosure as every other Graph-facing"
echo "    code in this project. Send one real test email through a connected Outlook mailbox"
echo "    and confirm: DeliveryQueueItem.provider_message_id is now populated (previously"
echo "    always None), a new EmailMessage(direction=outbound) row exists with a real"
echo "    internet_message_id, and a new Conversation/ConversationParticipant were created."
echo "  - GmailProvider.send() now sets a self-minted Message-ID header - confirm a real Gmail"
echo "    send still delivers successfully with this extra header present."
echo "  - The Mail.Read/Reconnect-scope gap from M6.2 is still open (unchanged by M6.3) - real"
echo "    end-to-end reply-correlation (an actual inbound reply landing in the right"
echo "    Conversation) still requires that follow-up or a manually re-scoped connection."
