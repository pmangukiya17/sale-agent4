#!/usr/bin/env bash
# Outlook Integration milestone - CEO-directed, found during live testing
# of Track C5's Executive Daily Brief: outbound send was failing with a
# permanent Graph 403, and mailbox sync was never importing anything.
# Root-caused (not guessed - see the conversation record and this
# script's own header comments below) to TWO independent, narrow issues,
# both fixed here with an OAuth-authorization-flow-only change:
#
#   1. app/delivery/providers/outlook_provider.py: send_scopes was
#      missing Mail.ReadWrite. M6.3 switched send() from a single
#      POST /me/sendMail call (needs only Mail.Send) to a create-draft-
#      then-send pattern (POST /me/messages, then
#      POST /me/messages/{id}/send) - creating a draft via
#      POST /me/messages requires Mail.ReadWrite, which was never added
#      to send_scopes. Every token issued before this fix had Mail.Send
#      but not Mail.ReadWrite, so the draft-creation call - step 1 of 2 -
#      was rejected with a PERMANENT 403 before the send step ever ran.
#   2. Every real Outlook connection only ever had send_scopes granted
#      (Mail.Send/User.Read/offline_access) - no route/UI anywhere ever
#      requested Mail.Read, so has_read_scope() correctly returned False
#      for every connection, and the already-real, already-tested
#      mailbox_sync_worker never had an eligible connection to sync.
#      Everything downstream (EmailMessage -> Thread Builder ->
#      Conversation -> Reply Intelligence -> Executive Daily Brief) was
#      waiting for data, not malfunctioning.
#
# Fix, per the CEO's explicit four requirements (no schema changes, no
# new workers, no architectural redesign, only the OAuth authorization
# flow changes):
#   A. OutlookProvider.send_scopes now includes Mail.ReadWrite.
#   B. connection_service.build_reconnect_authorize_url now always tops
#      up a connection to the provider's CURRENT send_scopes baseline
#      (previously it only ever replayed history, so a stale connection
#      would never have self-healed no matter how many times it
#      reconnected) - the pure list-math for this lives in the new,
#      zero-dependency app/delivery/scope_utils.py.
#   C. Mail.Read stays a SEPARATE, explicit opt-in - build_reconnect_
#      authorize_url only requests it when a caller passes
#      include_read_scopes=True (the new /reconnect?read_access=true
#      query param), never as a side effect of the baseline top-up.
#   D. DeliveryConnections.tsx now has two distinct actions per
#      connection - "Reconnect" (repairs send, never grants read access)
#      and "Enable Mailbox Reading" (shown only for a provider that
#      supports it, and only when not already granted) - plus two honest
#      status badges (Send: Ready/Needs Reconnect, Mailbox reading:
#      Enabled/Off) derived from scopes_granted, never fabricated.
#
# No new migration (still head 0026), no new worker service, no new
# route (one existing route gained one optional query param), no new
# database table or column - ProviderConnection.scopes_granted (JSONB,
# already existed) is what actually records the wider grant once a real
# user reconnects.
#
# Deliberately does NOT run `docker compose down -v` - same data-loss
# guard as every verify_*.sh before it.
set -euo pipefail

echo "=== 1/6: rebuild + boot ==="
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
echo "=== 2/6: confirm migration head unchanged (0026 - this milestone adds no migration) ==="
docker compose exec -T backend alembic current

echo
echo "=== 3/6: regression suites - confirm nothing this milestone touched broke anything upstream ==="
docker compose exec -T backend python -m unittest \
  tests.test_opportunity_state_machine \
  tests.test_opportunities_e2e \
  tests.test_pipeline_dashboard_metrics \
  tests.test_mailbox_brief_e2e \
  tests.test_outlook_provider_sync \
  tests.test_sync_worker_cursor_contract \
  tests.test_mailbox_sync_models \
  tests.test_thread_builder \
  tests.test_reply_intelligence_worker \
  tests.test_reply_intelligence_normalize \
  tests.test_conversation_resolver \
  -v

echo
echo "=== 4/6: new Outlook Integration test suites ==="
echo "-- pure scope-math (zero DB dependency - this one was actually run in the authoring sandbox too) --"
docker compose exec -T backend python -m unittest tests.test_scope_utils -v
echo "-- reconnect scope-union, DB-backed (first-ever test coverage for build_reconnect_authorize_url) --"
docker compose exec -T backend python -m unittest tests.test_connection_service_reconnect_scopes -v

echo
echo "=== 5/6: manual checklist - requires a real, live Outlook mailbox with actual unread mail ==="
echo "-- SEND FIX --"
echo "-- (a) On an EXISTING, already-connected Outlook connection: click Reconnect (not 'Enable Mailbox"
echo "--     Reading') - confirm the 'Send: Ready' badge appears afterward, confirm scopes_granted (GET"
echo "--     .../provider-connections/{id}) now includes Mail.ReadWrite --"
echo "-- (b) Send a real outbound email through a sending profile on that connection - confirm it lands in"
echo "--     the recipient's inbox, confirm the Delivery queue item shows a SUCCESS status, confirm"
echo "--     last_error is empty (no more 'Graph rejected the draft (403)') --"
echo "-- READ / SYNC FIX --"
echo "-- (c) Click 'Enable Mailbox Reading' on that same connection - complete Microsoft's consent screen -"
echo "--     confirm the 'Mailbox reading: Enabled' badge appears --"
echo "-- (d) Wait one MAILBOX_SYNC_POLL_INTERVAL_SECONDS tick (60s) - confirm mailbox_sync_worker logs a"
echo "--     non-zero synced count and EmailMessage rows now exist for this connection --"
echo "-- (e) Confirm thread_builder_worker's next tick creates/attaches Conversation + ConversationParticipant"
echo "--     rows for those inbound messages (conversation_id no longer NULL) --"
echo "-- (f) Confirm reply_intelligence_worker populates reply_status/needs_human_review on the resulting"
echo "--     Conversation(s) --"
echo "-- (g) Open the Conversations page - confirm real threads now appear --"
echo "-- (h) Open the Executive Daily Brief, click Regenerate - confirm Urgent Replies/Follow-ups Due/"
echo "--     Pipeline Snapshot now show real, non-zero data, and the Executive Summary paragraph's numbers"
echo "--     actually changed - the exact original symptom, now a concrete pass/fail check --"
echo "-- END-TO-END REPLY THREADING --"
echo "-- (i) Reply to the outbound email sent in step (b) from the recipient's side - confirm the NEXT sync"
echo "--     tick updates the SAME existing Conversation (reply_status/last_reply_at change on the same"
echo "--     conversation_id) rather than creating a duplicate Conversation - this is the real-world proof"
echo "--     that Graph's own internetMessageId/conversationId (captured at send time, per outlook_provider.py's"
echo "--     send() docstring) correctly threads an inbound reply back to the outbound send that started it --"
echo "-- TENANT ISOLATION --"
echo "-- (j) Repeat (a)-(h) for a SECOND business's Outlook connection - confirm its EmailMessage/"
echo "--     Conversation/Brief data never appears under the first business, and vice versa --"

echo
echo "ALL AUTOMATED CHECKS COMPLETE"
echo
echo "NOT covered by anything above - disclosed, deferred concerns:"
echo "  - This sandbox has neither Docker nor a working 'sqlalchemy' import (confirmed: 'ModuleNotFoundError:"
echo "    No module named sqlalchemy'), so only tests.test_scope_utils was actually executed while authoring"
echo "    this milestone - every other suite above, including the new"
echo "    tests.test_connection_service_reconnect_scopes, is py_compile-checked only until run here for real."
echo "  - No live Microsoft Graph call of any kind was made while authoring this fix - the root cause was"
echo "    identified from the code's own logic and its own error-string match to the CEO's reported message,"
echo "    not from reproducing the 403 directly. Steps (a)-(j) above are what actually proves the fix against"
echo "    a real Microsoft 365 tenant."
echo "  - Gmail is unaffected by, and unrelated to, this milestone: it has no IncrementalSyncCapable/"
echo "    MailboxReadCapable implementation at all (not a scope gap - a missing engine), and its send() uses a"
echo "    single-call users.messages.send with a locally-authored MIME message, never the create-draft"
echo "    pattern that needed Mail.ReadWrite for Outlook."
