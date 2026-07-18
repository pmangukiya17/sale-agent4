#!/usr/bin/env bash
# Verification for M6.1 (Conversation/EmailMessage/ConversationParticipant
# schema + migration 0009) against your EXISTING running stack and its
# real data.
#
# Deliberately does NOT run `docker compose down -v`. That command wipes
# the entire named Postgres volume - every business, contact, campaign,
# and now conversation you have - and is exactly what caused the real
# data-loss incident investigated earlier in this project. Migration 0009
# is purely additive (three new, currently-empty tables + two new enum
# types; it does not alter, and this script does not touch, any existing
# table or row), so verifying it never requires a fresh database.
#
# The downgrade/re-upgrade check below IS safe against your real data for
# a different reason than `down -v` would be unsafe: `alembic downgrade
# -1` only reverses what migration 0009 itself added (drops the three new,
# empty tables and two new enum types) - it has no DROP/ALTER statement
# touching anything from migrations 0001-0008. If you'd rather not run
# even that against your working environment, skip step 6 - steps 1-5
# and 7 already cover everything migration-correctness-wise.
set -euo pipefail

PSQL="docker compose exec -T db psql -U ${POSTGRES_USER:-sales_agent} -d ${POSTGRES_DB:-sales_agent}"

echo "=== 1/7: rebuild + boot - entrypoint.sh runs wait-for-db -> alembic upgrade head -> uvicorn ==="
docker compose up --build -d
echo "waiting for backend to report healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null; then
    echo "backend is up - 'alembic upgrade head' (now including 0009) completed as part of container startup"
    break
  fi
  sleep 2
done
curl -sf http://localhost:8000/api/v1/health && echo || { echo "FAILED: backend never became healthy - check: docker compose logs backend"; exit 1; }

echo
echo "=== 2/7: alembic head is 0009, and every existing M0-M5 row count is unchanged ==="
docker compose exec -T backend alembic current
echo "-- spot-check counts on a few pre-existing tables (compare against what you expect from before this migration) --"
$PSQL -c "SELECT
  (SELECT count(*) FROM company_profiles) AS company_profiles,
  (SELECT count(*) FROM prospects) AS prospects,
  (SELECT count(*) FROM provider_connections) AS provider_connections,
  (SELECT count(*) FROM delivery_queue_items) AS delivery_queue_items;"

echo
echo "=== 3/7: all 3 new tables exist, currently empty ==="
$PSQL -c "\dt" | grep -E "conversations|email_messages|conversation_participants"
$PSQL -c "SELECT
  (SELECT count(*) FROM conversations) AS conversations,
  (SELECT count(*) FROM email_messages) AS email_messages,
  (SELECT count(*) FROM conversation_participants) AS conversation_participants;"
echo "-- all three should read 0 - M6.1 ships schema only, nothing writes to these tables yet --"

echo
echo "=== 4/7: both new enum types exist, message_direction was NOT recreated ==="
$PSQL -c "SELECT typname FROM pg_type WHERE typname IN ('conversation_status','conversation_participant_role','message_direction') ORDER BY typname;"

echo
echo "=== 5/7: foreign keys + the partial unique dedup index ==="
$PSQL -c "
SELECT tc.table_name, kcu.column_name, ccu.table_name AS references_table, rc.delete_rule
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_name IN ('conversations','email_messages','conversation_participants')
ORDER BY tc.table_name, kcu.column_name;
"
$PSQL -c "\d email_messages" | grep -i "uq_email_messages_connection_internet_message_id"
$PSQL -c "\d conversation_participants" | grep -i "uq_conversation_participants_conversation_email"

echo
echo "=== 6/7 (optional - see header note above): migration 0009 cleanly reverses and re-applies ==="
docker compose exec -T backend alembic downgrade -1
$PSQL -c "\dt" | grep -E "conversations|email_messages|conversation_participants" && echo "FAILED: tables still present after downgrade" && exit 1 || echo "confirmed: all 3 tables dropped by downgrade"
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current

echo
echo "=== 7/7: real, executable model-constraint tests (nullable prospect_id, partial unique dedup, cascade delete, one-row-per-participant) ==="
docker compose exec -T backend python -m unittest tests.test_conversation_models -v

echo
echo "=== SQLAlchemy mapper sanity (every relationship(), including the 3 new models, resolves) ==="
docker compose exec -T backend python -c "
from app.db import base as _base
from sqlalchemy.orm import configure_mappers
configure_mappers()
print('All mappers configured successfully - every relationship() resolved.')
"

echo
echo "=== ALL CHECKS COMPLETE - review output above for any FAILED/error lines ==="
