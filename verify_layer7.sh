#!/usr/bin/env bash
# Verification for M5 Layer 7 (Integration & Final Verification) against
# the real Docker environment. Run from the repo root, AFTER
# verify_layer6.sh has already passed.
#
# What this covers, for real: the full stack (backend + worker + frontend)
# built and started together, then exercised end-to-end via the extended
# smoke_test.py (46 steps - all of M0-M4 plus 12 new M5 steps), the full
# backend unit test suite, and a direct-DB proof of the worker's
# crash-recovery path (reclaim_stale_claims), which has no HTTP route and
# so can't be reached through smoke_test.py's client-only design.
#
# The centerpiece is smoke_test.py steps 41/44: with no real Gmail/Outlook
# OAuth credentials available in this environment (a structural fact, not
# a sandbox limitation - no CI environment can complete a real OAuth
# consent screen unattended), those steps instead wait for the real
# `worker` container to claim and dispatch a queue item on its own clock,
# and assert it reaches the deterministic, credential-free FAILED outcome
# dispatch_service.dispatch() produces when a SendingProfile has no usable
# ProviderConnection. That is a genuine, unmocked, full-stack proof that
# worker polling, SELECT...FOR UPDATE SKIP LOCKED claiming, dispatch_service,
# DeliveryEvent logging, and campaign completion-checking are all wired
# together correctly - the one thing this milestone's automated
# verification CAN prove without a human in the loop.
#
# What this script deliberately does NOT attempt, and why:
#   - A real send through Gmail/Outlook - requires a human to complete a
#     real OAuth consent screen; see the required manual gate printed at
#     the end of this script.
#   - A multi-worker SKIP LOCKED concurrency stress test - deferred per
#     an explicit product decision, since docker-compose.yml runs exactly
#     one worker replica today; see docs/architecture/m5-production-readiness.md
#     for the "verify before scaling" note this defers to.
set -euo pipefail

echo "=== 1/5: rebuild backend + worker + frontend (smoke_test.py extension only, no app code changed in Layer 7) ==="
docker compose build backend worker frontend

echo
echo "=== 2/5: bring the FULL stack up, including the worker (smoke_test.py's M5 steps need it running on its own clock) ==="
docker compose up -d
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null; then break; fi
  sleep 2
done
curl -sf http://localhost:8000/api/v1/health && echo || { echo "FAILED: backend never became healthy"; exit 1; }
for i in $(seq 1 30); do
  if curl -sf http://localhost:5173/ > /dev/null; then break; fi
  sleep 2
done
curl -sf http://localhost:5173/ > /dev/null && echo "OK - frontend reachable" || { echo "FAILED: frontend never became reachable"; exit 1; }
echo "OK - worker container status: $(docker compose ps worker --format '{{.Status}}')"

echo
echo "=== 3/5: full smoke test - 46 steps, M0 through M5, against the real running stack (this is the main event; expect this to take a couple of minutes because of the M5 worker-poll waits) ==="
python3 smoke_test.py

echo
echo "=== 4/5: full backend unit test suite (regression check - covers the worker mapper-init fix, the retry_now/campaign-reactivation fix, and the IntegrityError->CampaignServiceError guard found and fixed during Layer 7 verification itself) ==="
docker compose exec -T backend python -m unittest discover -s tests -v

echo
echo "=== 5/5: worker crash-recovery path (reclaim_stale_claims) - direct DB manipulation, since this is internal worker infrastructure with no HTTP route a real client could ever hit ==="
docker compose exec -T backend python3 <<'PYEOF'
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.delivery.worker import reclaim_stale_claims
from app.models.delivery_campaign import DeliveryCampaign
from app.models.delivery_queue_item import DeliveryQueueItem
from app.models.enums import DeliveryQueueItemStatus

db = SessionLocal()
try:
    # Reuses the queue item from smoke_test.py's very first M5 campaign
    # (name is stable/deterministic - see smoke_test.py's
    # check_create_delivery_campaign) rather than constructing a whole new
    # Campaign/SendingProfile/OutreachDraft FK graph by hand just for this
    # check. Its current status doesn't matter - reclaim_stale_claims only
    # looks at status=SENDING + an old claimed_at, so this test forces
    # exactly that state directly, the same way a real worker crash would
    # leave it.
    campaign = db.scalar(
        select(DeliveryCampaign).where(DeliveryCampaign.name == "Smoke Test Campaign").order_by(DeliveryCampaign.created_at.desc())
    )
    if campaign is None:
        raise SystemExit("FAILED: no 'Smoke Test Campaign' found - run smoke_test.py (step 3/5 above) before this check")

    item = db.scalar(select(DeliveryQueueItem).where(DeliveryQueueItem.delivery_campaign_id == campaign.id))
    if item is None:
        raise SystemExit("FAILED: campaign has no queue item")

    stale_cutoff_minutes = settings.DELIVERY_WORKER_STALE_CLAIM_MINUTES
    item.status = DeliveryQueueItemStatus.SENDING
    item.claimed_at = datetime.now(timezone.utc) - timedelta(minutes=stale_cutoff_minutes + 5)
    db.commit()
    print(f"OK - forced queue item {item.id} into SENDING with claimed_at {stale_cutoff_minutes + 5}min ago (cutoff is {stale_cutoff_minutes}min)")

    reclaimed = reclaim_stale_claims()
    if reclaimed < 1:
        raise SystemExit(f"FAILED: reclaim_stale_claims() reclaimed {reclaimed} items, expected at least 1")
    print(f"OK - reclaim_stale_claims() reclaimed {reclaimed} item(s)")

    db.refresh(item)
    if item.status != DeliveryQueueItemStatus.SCHEDULED:
        raise SystemExit(f"FAILED: expected item status=SCHEDULED after reclaim, got {item.status}")
    if item.claimed_at is not None:
        raise SystemExit(f"FAILED: expected claimed_at=None after reclaim, got {item.claimed_at}")
    print(f"OK - queue item {item.id} correctly reset to SCHEDULED with claimed_at cleared - the worker's crash-recovery path works.")
finally:
    db.close()
PYEOF

echo
echo "=== NOT covered by this script - requires a human and real provider credentials, and cannot be automated in ANY environment ==="
echo "  REQUIRED before M5 is considered done, not optional:"
echo "  [ ] At least one real send via a real Gmail account (real Google Cloud OAuth client, real consent screen, real GmailProvider.send() call)"
echo "  [ ] At least one real send via a real Microsoft 365/Outlook account (real Azure app registration, real consent screen, real OutlookProvider.send() call)"
echo "  Deferred by explicit decision, not a gap:"
echo "  [ ] Multi-worker SKIP LOCKED concurrency stress test - only relevant if/when docker-compose.yml is ever changed to run worker replicas > 1"
echo
echo "=== ALL AUTOMATED CHECKS COMPLETE - review output above for any FAILED/error lines. Once the manual gates above are also confirmed, M5 is ready to be tagged M5-Stable. ==="
