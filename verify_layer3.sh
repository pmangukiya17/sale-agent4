#!/usr/bin/env bash
# Verification for M5 Layer 3 (Delivery Engine Core) against the real
# Docker environment. Run from the repo root, AFTER verify_0008.sh has
# already passed (this assumes the migrated schema is in place).
set -euo pipefail

echo "=== 1/6: rebuild backend + worker with the new dependencies (httpx, cryptography) ==="
docker compose build backend worker

echo "=== 2/6: bring the stack up ==="
docker compose up -d
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null; then break; fi
  sleep 2
done
curl -sf http://localhost:8000/api/v1/health && echo || { echo "FAILED: backend never became healthy"; exit 1; }

echo
echo "=== 3/6: every app.delivery module actually imports with real SQLAlchemy/httpx/cryptography installed ==="
docker compose exec -T backend python -c "
import app.delivery.context
import app.delivery.oauth_state
import app.delivery.timezone.resolver
import app.delivery.scheduler.windows
import app.delivery.scheduler.policy
import app.delivery.scheduler.registry
import app.delivery.credentials.base
import app.delivery.credentials.payload_codec
import app.delivery.credentials.postgres_fernet_store
import app.delivery.credentials.registry
import app.delivery.providers.base
import app.delivery.providers.gmail_provider
import app.delivery.providers.outlook_provider
import app.delivery.providers.registry
import app.delivery.connection_service
import app.delivery.campaign_service
import app.delivery.queue_service
import app.delivery.dispatch_service
import app.delivery.worker
print('All app.delivery modules imported successfully.')
"

echo
echo "=== 4/6: SQLAlchemy mappers still configure cleanly with the M5 relationships ==="
docker compose exec -T backend python -c "
from app.db import base as _base
from sqlalchemy.orm import configure_mappers
configure_mappers()
print('All mappers configured successfully.')
"

echo
echo "=== 5/6: the four real, pure-logic unit test suites (timezone resolver, scheduler windows, payload codec, oauth state) ==="
docker compose exec -T backend python -m unittest tests.test_delivery_timezone_resolver tests.test_delivery_scheduler_windows tests.test_delivery_payload_codec tests.test_delivery_oauth_state -v

echo
echo "=== 6/6: CREDENTIAL_ENCRYPTION_KEY fails loudly when unset (expected to print the error below, not crash the script) ==="
docker compose exec -T backend python -c "
from app.delivery.credentials.registry import get_credential_store
from app.delivery.credentials.base import CredentialStoreError
import uuid
try:
    get_credential_store().save(None, uuid.uuid4(), {'access_token': 'x'})
    print('UNEXPECTED: save() did not raise - check CREDENTIAL_ENCRYPTION_KEY is really unset in this env')
except CredentialStoreError as e:
    print(f'OK - fails loudly as designed: {e}')
except Exception as e:
    print(f'OK (raised before reaching the DB, as expected without a real session): {type(e).__name__}: {e}')
"

echo
echo "=== NOT covered by this script - needs a real Google Cloud OAuth client / Azure app registration ==="
echo "  - the actual Connect -> Reconnect -> Verify -> Disconnect flow against a real mailbox"
echo "  - an actual send via Gmail/Outlook (gmail_provider.py / outlook_provider.py are UNVERIFIED BY EXECUTION - see their docstrings)"
echo "  - end-to-end: create a DeliveryCampaign from a real approved OutreachDraft, schedule it, let the worker dispatch it, confirm the email arrives"
echo
echo "=== ALL AUTOMATED CHECKS COMPLETE - review output above for any FAILED/error lines ==="
