#!/usr/bin/env bash
# One-shot verification of migration 0008 (M5 Layer 2) against a real,
# freshly-created Postgres via Docker Compose. Run from the repo root.
set -euo pipefail

echo "=== 1/7: truly fresh DB (drops the named Postgres volume too) ==="
docker compose down -v

echo "=== 2/7 + 7/7: rebuild and boot - entrypoint.sh runs wait-for-db -> alembic upgrade head -> uvicorn ==="
docker compose up --build -d
echo "waiting for backend to report healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null; then
    echo "backend is up - 'alembic upgrade head' completed as part of container startup"
    break
  fi
  sleep 2
done
curl -sf http://localhost:8000/api/v1/health && echo || { echo "FAILED: backend never became healthy - check: docker compose logs backend"; exit 1; }

echo
echo "=== 3/7: all 6 new tables exist ==="
docker compose exec -T db psql -U "${POSTGRES_USER:-sales_agent}" -d "${POSTGRES_DB:-sales_agent}" -c "\dt" | grep -E "provider_connections|provider_credentials|sending_profiles|delivery_campaigns|delivery_queue_items|delivery_events"

echo
echo "=== 4/7: all 4 new enum types exist ==="
docker compose exec -T db psql -U "${POSTGRES_USER:-sales_agent}" -d "${POSTGRES_DB:-sales_agent}" -c "SELECT typname FROM pg_type WHERE typname IN ('provider_connection_status','delivery_campaign_status','delivery_queue_item_status','delivery_event_type') ORDER BY typname;"

echo
echo "=== 5/7: foreign keys on the 6 new tables ==="
docker compose exec -T db psql -U "${POSTGRES_USER:-sales_agent}" -d "${POSTGRES_DB:-sales_agent}" -c "
SELECT tc.table_name, kcu.column_name, ccu.table_name AS references_table, rc.delete_rule
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_name IN ('provider_connections','provider_credentials','sending_profiles','delivery_campaigns','delivery_queue_items','delivery_events')
ORDER BY tc.table_name, kcu.column_name;
"

echo
echo "=== 5/7 (cont.): the partial unique index on delivery_queue_items ==="
docker compose exec -T db psql -U "${POSTGRES_USER:-sales_agent}" -d "${POSTGRES_DB:-sales_agent}" -c "\d delivery_queue_items" | grep -i "uq_delivery_queue_items_active_draft"

echo
echo "=== 6/7: countries timezone backfill applied ==="
docker compose exec -T db psql -U "${POSTGRES_USER:-sales_agent}" -d "${POSTGRES_DB:-sales_agent}" -c "SELECT code, default_timezone FROM countries ORDER BY code LIMIT 8;"
echo "-- sanity count: should be 35 (all seeded countries) --"
docker compose exec -T db psql -U "${POSTGRES_USER:-sales_agent}" -d "${POSTGRES_DB:-sales_agent}" -c "SELECT count(*) AS backfilled FROM countries WHERE default_timezone IS NOT NULL;"

echo
echo "=== SQLAlchemy started cleanly (implied by the healthy /health check above, plus this direct mapper check) ==="
docker compose exec -T backend python -c "
from app.db import base as _base
from sqlalchemy.orm import configure_mappers
configure_mappers()
print('All mappers configured successfully - every relationship() resolved.')
"

echo
echo "=== ALL CHECKS COMPLETE - review output above for any FAILED/error lines ==="
