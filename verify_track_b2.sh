#!/usr/bin/env bash
# Track B2 verification: the three areas comprehensive-verification-matrix.md's
# Group 3 (rows 35-37) reserved for a dedicated pass after Track B1 -
# ProspectContact archive/delete lifecycle, the legacy Company/Contact
# tenant-isolation gap (re-confirming it's the accepted one, not fixing
# it), and the /auth/register admin gate + bootstrap exception.
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_*.sh before it.
#
# What this script CANNOT verify (disclosed up front):
#   - The bootstrap-exception branch in register() (row 37) as OBSERVED
#     LIVE-API BEHAVIOR. app.main's own ensure_first_admin() runs during
#     FastAPI's startup lifespan, before the server accepts its first
#     request, and seeds a real admin the instant `users` has zero rows -
#     so by the time this script's `docker compose up` health check below
#     succeeds, is_bootstrap is already permanently False for this
#     container's lifetime. tests.test_track_b2_verification's own
#     TestAuthRegistrationBootstrapException class exercises that branch
#     directly (bypassing ensure_first_admin() by calling register()
#     itself), so step 3 below will very likely report those two tests
#     SKIPPED, not failed - that is the expected, honest outcome in this
#     environment, not a bug in the test. Seeing them skip is itself a
#     confirmation of the finding: this branch is real defensive code,
#     but not one a live deployment's first real registration call will
#     ever actually hit.
#   - No live AI provider call is made anywhere in this script.
set -euo pipefail

echo "=== 1/4: rebuild + boot ==="
docker compose up --build -d
echo "waiting for backend to report healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null; then
    echo "backend is up"
    break
  fi
  sleep 2
done
curl -sf http://localhost:8000/api/v1/health && echo || { echo "FAILED: backend never became healthy - check: docker compose logs backend"; exit 1; }

echo
echo "=== 2/4: confirm the RESTRICT migrations (0023/0024) are actually applied ==="
docker compose exec -T backend python -c "
from app.db.session import SessionLocal
from sqlalchemy import text
db = SessionLocal()
row = db.execute(text(\"SELECT confdeltype FROM pg_constraint WHERE conname = 'outreach_requests_prospect_contact_id_fkey'\")).scalar()
db.close()
assert row == 'r', f'expected RESTRICT (r), got {row!r} - migration 0023 may not be applied'
print('confirmed: outreach_requests.prospect_contact_id is RESTRICT, not CASCADE')
"

echo
echo "=== 3/4: Track B2 automated suite (row 35 ProspectContact lifecycle, row 36 legacy isolation gap re-check, row 37 auth registration gate) ==="
docker compose exec -T backend python -m unittest tests.test_track_b2_verification -v

echo
echo "=== 4/4: manual checklist (no automated coverage exists for these - see comprehensive-verification-matrix.md) ==="
echo "-- row 35: in the browser, open a Prospect with an archived contact and confirm it's hidden from the default contact list, then reappears under an 'Archived' view/toggle if the UI exposes one --"
echo "-- row 37: confirm POST /api/v1/auth/register in Swagger UI (http://localhost:8000/docs) actually 403s when called with no Authorization header and at least one user already exists --"

echo
echo "ALL CHECKS COMPLETE"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - The bootstrap-exception branch's live-API reachability - see this script's own header; it's structurally"
echo "    unreachable in any already-booted deployment, by design of ensure_first_admin(), not a gap in this script."
echo "  - The legacy Company/Contact isolation gap (row 36) is verified as UNCHANGED from the accepted, documented"
echo "    state (deferred-items-and-design-boundaries.md item 6) - this script proves the gap didn't get WORSE and"
echo "    hasn't leaked into the real tenant boundary, not that the gap itself was fixed (it was deliberately not)."
echo "  - No concurrent-request race test for the bootstrap exception's known narrow window (two simultaneous"
echo "    unauthenticated registers on a truly empty DB) - documented as a known, accepted limitation in"
echo "    deferred-items-and-design-boundaries.md, not exercised here."
