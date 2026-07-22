#!/usr/bin/env bash
# Verification for M5 Layer 5 (API routes) against the real Docker
# environment. Run from the repo root, AFTER verify_layer4.sh has already
# passed. Covers what this sandbox could not: FastAPI/pydantic/SQLAlchemy
# are not installed here (no PyPI access - the standing environment
# limitation disclosed since Layer 2), so route registration, OpenAPI
# schema generation, and live HTTP behavior could only be checked
# statically (py_compile across the whole tree, an AST-based cross-module
# import-resolution check, and a purpose-built static route-collision
# checker that specifically verifies literal path segments like "connect"
# and "callback" are registered before the {connection_id} routes that
# would otherwise shadow them - a real bug class this project already
# follows the precedent for, see outreach_drafts.py's "current" route).
set -euo pipefail

echo "=== 1/6: rebuild backend + worker (main.py, providers/base.py, connection_service.py, oauth_state.py all changed) ==="
docker compose build backend worker

echo "=== 2/6: bring the stack up ==="
docker compose up -d
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null; then break; fi
  sleep 2
done
curl -sf http://localhost:8000/api/v1/health && echo || { echo "FAILED: backend never became healthy"; exit 1; }

echo
echo "=== 3/6: every new/changed module imports cleanly, and the FastAPI app itself builds (registers all routers without raising) ==="
docker compose exec -T backend python -c "
import app.api.routes.sending_profiles
import app.api.routes.delivery_campaigns
import app.api.routes.delivery_queue_items
import app.api.routes.provider_connections
import app.main
print('app.main imported successfully - every router (including the 4 new M5 ones) registered without raising.')
"

echo
echo "=== 4/6: OpenAPI schema generation succeeds, and specifically proves the connect/{connection_id} route-ordering fix actually worked (both appear as DISTINCT operations, not one shadowing the other) ==="
docker compose exec -T backend python -c "
from app.main import app
schema = app.openapi()
paths = schema['paths']

must_exist = [
    ('/api/v1/delivery/providers', 'get'),
    ('/api/v1/company-profiles/{company_profile_id}/sending-profiles', 'post'),
    ('/api/v1/company-profiles/{company_profile_id}/sending-profiles/{sending_profile_id}', 'delete'),
    ('/api/v1/company-profiles/{company_profile_id}/provider-connections/connect', 'get'),
    ('/api/v1/company-profiles/{company_profile_id}/provider-connections/callback', 'post'),
    ('/api/v1/company-profiles/{company_profile_id}/provider-connections/{connection_id}', 'get'),
    ('/api/v1/company-profiles/{company_profile_id}/provider-connections/{connection_id}/reconnect', 'get'),
    ('/api/v1/company-profiles/{company_profile_id}/provider-connections/{connection_id}/disconnect', 'post'),
    ('/api/v1/company-profiles/{company_profile_id}/provider-connections/{connection_id}/verify', 'post'),
    ('/api/v1/company-profiles/{company_profile_id}/delivery-campaigns', 'post'),
    ('/api/v1/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}/schedule', 'post'),
    ('/api/v1/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}/cancel', 'post'),
    ('/api/v1/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}/queue-items', 'get'),
    ('/api/v1/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}/queue-items/{item_id}/cancel', 'post'),
    ('/api/v1/company-profiles/{company_profile_id}/delivery-campaigns/{campaign_id}/queue-items/{item_id}/retry', 'post'),
]
missing = [(p, m) for p, m in must_exist if p not in paths or m not in paths[p]]
if missing:
    raise SystemExit(f'FAILED: missing operations: {missing}')

# The actual regression this specifically guards against: if the
# connect/{connection_id} route ordering bug were reintroduced, FastAPI
# would still register both as distinct string paths (OpenAPI doesn't
# collapse literal vs param paths that differ in raw text) - so this
# check alone can't catch the runtime shadowing. That's confirmed live
# in step 6 below via a real HTTP call to .../connect.
print(f'OK - OpenAPI schema generated successfully with {len(paths)} total paths; all {len(must_exist)} expected M5 Layer 5 operations present.')
"

echo
echo "=== 5/6: the full pure-logic unit test suite (37 tests - includes the new oauth_state signing/tamper/expiry tests) ==="
docker compose exec -T backend python -m unittest discover -s tests -v

echo
echo "=== 6/6: live HTTP - proves the connect/{connection_id} route ordering fix actually works at runtime, not just in the OpenAPI schema ==="
docker compose exec -T backend python -c "
import httpx

BASE = 'http://localhost:8000/api/v1'
# Fixed (not random-suffixed) email: POST /auth/register is now admin-gated
# except for the very first user ever created on a fresh DB (see
# app/api/routes/auth.py's bootstrap exception, added alongside the
# ProspectContact/legacy-CRM architectural fixes). Re-running this script
# against a DB that already has that first user must reuse it via login
# rather than attempt another open register call, which would now 403.
email = 'layer5-verify@example.com'
password = 'verify-pass-123'
r = httpx.post(f'{BASE}/auth/login', data={'username': email, 'password': password}, timeout=10)
if r.status_code != 200:
    r = httpx.post(f'{BASE}/auth/register', json={'email': email, 'full_name': 'Layer5 Verify', 'password': password}, timeout=10)
    assert r.status_code == 201, f'register failed: {r.status_code} {r.text}'
    r = httpx.post(f'{BASE}/auth/login', data={'username': email, 'password': password}, timeout=10)
assert r.status_code == 200, f'login failed: {r.status_code} {r.text}'
token = r.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

r = httpx.post(f'{BASE}/company-profiles', json={'name': 'Layer 5 Verify Co'}, headers=headers, timeout=10)
assert r.status_code == 201, f'company profile create failed: {r.status_code} {r.text}'
company_id = r.json()['id']

# GET .../provider-connections/connect with an UNCONFIGURED provider still
# reaches start_provider_connect (proving it is NOT shadowed by
# {connection_id} trying and failing to parse 'connect' as a UUID, which
# would surface as a 422, not the 400 this should actually return since
# no OAuth client id/secret are set in this environment).
r = httpx.get(f'{BASE}/company-profiles/{company_id}/provider-connections/connect', params={'provider_key': 'gmail'}, headers=headers, timeout=10)
assert r.status_code == 400, f'expected 400 (gmail not configured in this env), got {r.status_code}: {r.text} - a 422 here would mean the route-ordering bug is back'
print(f'OK - /provider-connections/connect reached start_provider_connect correctly (400, not 422): {r.json()[\"detail\"]}')

r = httpx.get(f'{BASE}/delivery/providers', headers=headers, timeout=10)
assert r.status_code == 200, f'{r.status_code} {r.text}'
print(f'OK - GET /delivery/providers -> {r.json()} (empty is expected/correct: no OAuth client id/secret configured in this env)')

r = httpx.get(f'{BASE}/company-profiles/{company_id}/sending-profiles', headers=headers, timeout=10)
assert r.status_code == 200 and r.json() == [], f'{r.status_code} {r.text}'
print('OK - GET sending-profiles for a fresh company profile -> 200, empty list')

r = httpx.post(f'{BASE}/company-profiles/{company_id}/sending-profiles', json={
    'provider_key': 'gmail', 'label': 'CEO', 'sender_name': 'Verify CEO', 'sender_email': 'ceo@example.com',
}, headers=headers, timeout=10)
assert r.status_code == 201, f'{r.status_code} {r.text}'
sending_profile_id = r.json()['id']
print(f'OK - created SendingProfile {sending_profile_id}')

r = httpx.post(f'{BASE}/company-profiles/{company_id}/delivery-campaigns', json={
    'sending_profile_id': sending_profile_id, 'name': 'Verify campaign', 'outreach_draft_ids': [str(uuid.uuid4())],
}, headers=headers, timeout=10)
assert r.status_code == 400, f'expected 400 (the draft id does not exist), got {r.status_code}: {r.text}'
print(f'OK - DeliveryCampaign create with a bogus outreach_draft_id correctly rejected via CampaignServiceError -> 400: {r.json()[\"detail\"]}')

print()
print('ALL LIVE HTTP CHECKS PASSED.')
"

echo
echo "=== NOT covered by this script - needs a real Google Cloud OAuth client / Azure app registration and a real approved OutreachDraft ==="
echo "  - the actual Connect -> Google/Microsoft consent -> callback -> Verify -> Disconnect round trip"
echo "  - a full DeliveryCampaign created from a real approved OutreachDraft, scheduled, and dispatched by the worker"
echo "  - the frontend's oauth callback page (does not exist until Layer 6)"
echo
echo "=== ALL AUTOMATED CHECKS COMPLETE - review output above for any FAILED/error lines ==="
