#!/usr/bin/env bash
# Verification for M5 Layer 4 (Schemas) against the real Docker
# environment. Run from the repo root, AFTER verify_layer3.sh has already
# passed. This sandbox has no pip/PyPI access, so pydantic itself could
# not be installed or executed here - everything below was checked by
# static means only (py_compile syntax check + an AST-based cross-module
# import-resolution check + a manual field-by-field cross-reference
# against each SQLAlchemy model's actual columns). This script performs
# the real, executable check that sandbox couldn't: constructing each
# schema with pydantic itself and confirming validators actually fire.
set -euo pipefail

echo "=== 1/3: bring the stack up (no new migration/dependency in this layer, so just confirm nothing broke) ==="
docker compose up -d
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null; then break; fi
  sleep 2
done
curl -sf http://localhost:8000/api/v1/health && echo || { echo "FAILED: backend never became healthy"; exit 1; }

echo
echo "=== 2/3: every new app.schemas module imports cleanly ==="
docker compose exec -T backend python -c "
import app.schemas.sending_profile
import app.schemas.provider_connection
import app.schemas.delivery_campaign
import app.schemas.delivery_event
import app.schemas.delivery_queue_item
print('All 5 new app.schemas modules imported successfully.')
"

echo
echo "=== 3/3: schemas actually construct with pydantic, and the two custom validators actually fire ==="
docker compose exec -T backend python -c "
import uuid
from datetime import datetime, time, timezone
from pydantic import ValidationError

from app.models.enums import DeliveryCampaignStatus, DeliveryEventType, DeliveryQueueItemStatus, ProviderConnectionStatus
from app.schemas.sending_profile import SendingProfileCreate, SendingProfileRead, SendingProfileUpdate
from app.schemas.provider_connection import ConnectableProviderRead, ProviderConnectionAuthorizeUrlRead, ProviderConnectionRead
from app.schemas.delivery_campaign import DeliveryCampaignCreate, DeliveryCampaignRead, DeliveryCampaignCancelBody
from app.schemas.delivery_event import DeliveryEventRead
from app.schemas.delivery_queue_item import DeliveryQueueItemRead, DeliveryQueueItemCancelBody

# --- SendingProfileCreate: valid input constructs ---
sp_create = SendingProfileCreate(
    provider_key='gmail', label='CEO', sender_name='Jane CEO', sender_email='jane@example.com',
    sending_timezone='Europe/Berlin', min_gap_seconds=60, max_gap_seconds=300,
)
assert sp_create.sending_timezone == 'Europe/Berlin'

# --- SendingProfileCreate: invalid IANA timezone rejected ---
try:
    SendingProfileCreate(provider_key='gmail', label='x', sender_name='x', sender_email='x@x.com', sending_timezone='Not/AZone')
    raise SystemExit('FAILED: invalid timezone was NOT rejected')
except ValidationError:
    pass

# --- SendingProfileCreate: max_gap < min_gap rejected ---
try:
    SendingProfileCreate(provider_key='gmail', label='x', sender_name='x', sender_email='x@x.com', min_gap_seconds=300, max_gap_seconds=60)
    raise SystemExit('FAILED: max_gap_seconds < min_gap_seconds was NOT rejected')
except ValidationError:
    pass

# --- DeliveryCampaignCreate: same gap-order validator, shared base class ---
try:
    DeliveryCampaignCreate(sending_profile_id=uuid.uuid4(), name='x', outreach_draft_ids=[uuid.uuid4()], min_gap_seconds=300, max_gap_seconds=60)
    raise SystemExit('FAILED: DeliveryCampaignCreate did not reject max_gap < min_gap')
except ValidationError:
    pass
dc_create = DeliveryCampaignCreate(sending_profile_id=uuid.uuid4(), name='Q3 outreach', outreach_draft_ids=[uuid.uuid4(), uuid.uuid4()])
assert dc_create.respect_recipient_timezone is True and dc_create.priority == 0

# --- SendingProfileUpdate: every field genuinely optional (partial update) ---
sp_update = SendingProfileUpdate(label='Renamed')
assert sp_update.label == 'Renamed' and sp_update.sender_email is None

# --- Read schemas: from_attributes works against a plain object (stands in for an ORM instance) ---
class _FakeORM:
    def __init__(self, **kw):
        self.__dict__.update(kw)

now = datetime.now(timezone.utc)
fake_conn = _FakeORM(
    id=uuid.uuid4(), company_profile_id=uuid.uuid4(), provider_key='gmail', external_account_email='jane@gmail.com',
    scopes_granted=['gmail.send'], status=ProviderConnectionStatus.CONNECTED, connected_at=now, disconnected_at=None,
    last_verification_at=now, last_verified_at=now, last_verification_detail=None, created_at=now, updated_at=now,
)
conn_read = ProviderConnectionRead.model_validate(fake_conn)
assert conn_read.status == ProviderConnectionStatus.CONNECTED

fake_item = _FakeORM(
    id=uuid.uuid4(), delivery_campaign_id=uuid.uuid4(), outreach_draft_id=uuid.uuid4(), prospect_id=uuid.uuid4(),
    prospect_contact_id=uuid.uuid4(), company_profile_id=uuid.uuid4(), sending_profile_id=uuid.uuid4(), channel_key='email',
    frozen_content={'assembled': {'subject': 'hi'}}, frozen_draft_version=1, recipient_email='a@b.com', recipient_timezone='UTC',
    status=DeliveryQueueItemStatus.QUEUED, scheduled_send_at=None, sent_at=None, attempt_count=0, max_attempts=3,
    last_error=None, provider_message_id=None, claimed_at=None, cancelled_reason=None, events=[], created_at=now, updated_at=now,
)
item_read = DeliveryQueueItemRead.model_validate(fake_item)
assert item_read.claimed_at is None and item_read.status == DeliveryQueueItemStatus.QUEUED

fake_event = _FakeORM(id=uuid.uuid4(), delivery_queue_item_id=uuid.uuid4(), event_type=DeliveryEventType.QUEUED, occurred_at=now, detail=None)
event_read = DeliveryEventRead.model_validate(fake_event)
assert event_read.event_type == DeliveryEventType.QUEUED

# --- action/utility bodies construct with defaults ---
assert DeliveryQueueItemCancelBody().reason is None
assert DeliveryCampaignCancelBody(reason='paused indefinitely').reason == 'paused indefinitely'
assert ProviderConnectionAuthorizeUrlRead(authorize_url='https://accounts.google.com/o/oauth2/v2/auth?...').authorize_url.startswith('https://')
assert ConnectableProviderRead(provider_key='outlook', send_scopes=['Mail.Send', 'offline_access']).provider_key == 'outlook'

print('All Layer 4 schema checks passed: construction, from_attributes, and both custom validators (timezone, gap-order) behave as designed.')
"

echo
echo "=== NOT covered by this script - has no meaning until Layer 5 (routes) exists ==="
echo "  - actual HTTP request/response validation through FastAPI's own OpenAPI-driven validation layer"
echo "  - SendingProfileUpdate / DeliveryCampaignOverridesBase partial-update semantics under a real PATCH call"
echo
echo "=== ALL AUTOMATED CHECKS COMPLETE - review output above for any FAILED/error lines ==="
