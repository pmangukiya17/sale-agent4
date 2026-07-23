#!/usr/bin/env bash
# Track C5 (dashboard-capabilities-architecture-plan.md, Section 6):
# Mailbox Brief - a persisted, on-demand executive summary over existing
# CRM data. New migration 0026 (mailbox_briefs), new app/mailbox_brief/
# package (context.py, engine/ - a pluggable synthesis-engine interface
# with one deterministic implementation, service.py), new
# app/api/routes/mailbox_brief.py (2 endpoints), MailboxBrief.tsx wired to
# a real "Generate New Brief" action. The final one of the six
# capabilities this dashboard's placeholder review set out to resolve.
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_*.sh before it. This track DOES add a new
# migration (0026) - step 2 below runs `alembic upgrade head` explicitly,
# same convention verify_track_c3.sh already established.
#
# What this script CANNOT verify (disclosed up front):
#   - The frontend's real rendered appearance (Mailbox Brief showing a
#     real generated summary instead of "Not yet implemented", the
#     "Generate New Brief" button actually round-tripping, the breathing
#     glow firing once a brief exists) - `tsc -b --force` confirms the
#     frontend compiles; a live browser check is still needed for the
#     visual result, same standing limitation as every prior frontend-
#     touching verify script in this project.
#   - No live AI provider call anywhere in this track - the deterministic
#     engine (app/mailbox_brief/engine/deterministic_stub.py) is a
#     rule-based synthesis over already-stored data, the same
#     "deterministic stub now, real LLM engine later, zero schema
#     change" precedent app/personalization/engine/deterministic_stub.py
#     already set - no anthropic/openai/google-genai SDK is installed or
#     exercised anywhere in this track.
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
echo "=== 2/4: apply migration 0026 (mailbox_briefs) ==="
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current

echo
echo "=== 3/4: Track C5 test suite (generation, persistence, retrieval, regeneration, tenant isolation, empty workspace, edge cases) ==="
docker compose exec -T backend python -m unittest tests.test_mailbox_brief_e2e -v

echo
echo "=== 4/4: manual checklist (no automated coverage exists for these) ==="
echo "-- in the browser, confirm the Mailbox Brief card shows 'No brief has been generated yet' with a Generate Brief button --"
echo "-- click Generate Brief, confirm a real summary and (if any exist) recommendation rows appear, and the card's glow starts breathing --"
echo "-- reload the page - confirm the SAME brief is still shown (no silent auto-regeneration on page load) --"
echo "-- click Regenerate, confirm a NEW brief replaces the displayed one (generated_at timestamp changes) --"

echo
echo "ALL CHECKS COMPLETE"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - Visual confirmation of the widget's real content and breathing-glow behavior requires a live browser - see"
echo "    this script's own header."
echo "  - This completes all six dashboard capabilities from dashboard-capabilities-architecture-plan.md - no"
echo "    honest placeholders remain on the Command Center dashboard."
