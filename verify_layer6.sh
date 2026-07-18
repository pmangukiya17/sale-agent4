#!/usr/bin/env bash
# Verification for M5 Layer 6 (Frontend) against the real Docker
# environment. Run from the repo root, AFTER verify_layer5.sh has already
# passed.
#
# What this sandbox COULD verify, for real: `tsc -b --force --noEmit`
# ran clean (exit 0, zero errors) across the whole project - 43
# TypeScript/TSX files, strict mode on - which type-checks and resolves
# every module, including all 9 new/changed Layer 6 files. That's a real,
# executed check, not a static approximation.
#
# What this sandbox could NOT verify: `npm run build`'s second step
# (`vite build`) failed here with "Cannot find module
# @rollup/rollup-linux-arm64-gnu" - a known npm optional-dependencies bug
# (https://github.com/npm/cli/issues/4828), not a code issue. Confirmed
# by attempting `npm install @rollup/rollup-linux-arm64-gnu` directly,
# which hit the same 403-blocked-by-allowlist restriction already
# disclosed for pip/PyPI in earlier layers - this sandbox has no npm
# registry access either. Your local/CI environment (or the Docker image
# itself, built fresh) won't have this problem.
set -euo pipefail

echo "=== 1/4: rebuild frontend (new pages/components/hooks, new routes, Sidebar/Businesses.tsx changes) ==="
docker compose build frontend

echo
echo "=== 2/4: bring the stack up ==="
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
curl -sf http://localhost:5173/ > /dev/null && echo "OK - frontend dev server responding" || { echo "FAILED: frontend never became reachable"; exit 1; }

echo
echo "=== 3/4: full TypeScript build INSIDE the container (real npm registry access - the actual check this sandbox couldn't do) ==="
docker compose exec -T frontend npm run build

echo
echo "=== 4/4: the small Layer 5 addition (available-drafts) and the sending-profile provider-mismatch fix, both touched while building Layer 6 ==="
docker compose exec -T backend python -m unittest discover -s tests -v

echo
echo "=== NOT covered by this script - needs a browser and real Google/Microsoft OAuth credentials ==="
echo "  Manual checklist:"
echo "  [ ] Sidebar 'Delivery' link is greyed out with no business selected, becomes live once one is"
echo "  [ ] Delivery tabs (Campaigns/Sending Profiles/Connections) switch correctly, landing on Campaigns by default"
echo "  [ ] 'Connect Gmail'/'Connect Outlook' only appear if that provider's OAuth client id/secret are set in .env"
echo "  [ ] Full OAuth round trip: click Connect -> Google/Microsoft consent -> redirected to /oauth/callback -> lands back on Connections with the new mailbox listed"
echo "  [ ] Creating a SendingProfile rejects a provider_connection_id whose provider_key doesn't match (try it - should 400 with a clear message)"
echo "  [ ] Campaign creation picker only shows APPROVED, unqueued drafts; creating a campaign removes those drafts from the picker on next visit"
echo "  [ ] Campaign detail page's queue-items table visibly updates ~10s after the worker processes an item, without a manual refresh"
echo "  [ ] Polling actually stops once a campaign reaches Completed/Cancelled (check Network tab - no further queue-items requests)"
echo
echo "=== ALL AUTOMATED CHECKS COMPLETE - review output above for any FAILED/error lines ==="
