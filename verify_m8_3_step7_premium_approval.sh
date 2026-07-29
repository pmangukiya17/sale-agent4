#!/usr/bin/env bash
# M8.3 - AI Gateway Management & Control, STEP 7 ONLY (Premium Approval UI)
#
# Builds on Steps 1-6 (Provider Config, Provider Management UI, Model Role
# Management, Routing Simulator, Provider Capability Viewer, Gateway
# Diagnostics - all approved, verified, committed separately). Step 7
# exposes the EXISTING premium-approval-required workflow (AIGateway.complete()'s
# synchronous gate - M11/M-AIGW-1) through a scalable admin interface:
# Approve/Reject actions, an audit history, and a filterable queue - see
# docs/architecture/m8-3-ai-gateway-control-center-plan.md Section 13 for
# the full architecture review + implementation plan this step follows.
#
# CEO REVIEW (2026-07-29): plan approved with 5 required amendments, all
# incorporated below (see Section 13.1 of the plan doc for the CEO's own
# reasoning on each):
#   1. AIPremiumPreauthorization.company_profile_id FK -> RESTRICT, not
#      CASCADE (governance/audit record; protect business data).
#   2. AI_GATEWAY_PREMIUM_PREAUTH_MINUTES = 120, not 60 (realistic
#      submit -> admin unavailable -> approve later -> retry workflow).
#   3. Approve/Reject/History remain ADMIN-ONLY - no company-owner
#      permission tier introduced this step (consistency with every other
#      Gateway administration surface: Provider Management, Model Role
#      Management, Gateway Diagnostics).
#   4. Notifications deferred entirely - no publish call added this step.
#   5. Structural change: AIGateway no longer opens SessionLocal()/queries
#      SQLAlchemy directly for the premium-approval check - a new
#      PremiumApprovalResolver abstraction (app/ai_gateway/premium_approval_resolver.py)
#      is the ONLY seam AIGateway depends on
#      (AIGateway -> PremiumApprovalResolver -> Database implementation),
#      injected the same constructor-DI way `provider_lookup` already is
#      (M7.2 precedent).
#
# CEO REVIEW FIX (2026-07-29, first submission not approved): two issues
# reported against the first verification pass.
#
#   (1) test_preflight_reports_no_approval_needed_when_resolver_returns_true /
#       test_preflight_still_reports_approval_needed_when_resolver_returns_false
#       (tests/test_ai_provider_hierarchy_e2e.py) failed with resolver.calls==0
#       and approval_required==False regardless of what the injected resolver
#       returned - reported as "preflight() is no longer consulting the
#       injected resolver correctly." Root-caused via direct inspection of
#       client.py (preflight()'s own body already calls
#       `self._is_premium_preauthorized(request)`, identically to complete() -
#       confirmed unchanged, no fix needed there) plus a targeted reproduction:
#       both failing tests used `_AlwaysUnavailableProviderClient` (is_configured()
#       -> True, complete() raises at CALL time) for the chain's "local"
#       provider. preflight() deliberately never calls complete() - only
#       is_configured() (see its own docstring: "no network call") - so that
#       fixture made `chain_has_configured_candidate` True and preflight()
#       returned early, BEFORE the resolver was ever reached. This is the
#       EXACT fixture mistake TestPreflight's own
#       test_nothing_configured_in_chain_reports_approval_required_with_estimate
#       (same file, an earlier milestone) already documents and had already
#       been fixed for once - the two new Step 7 tests reintroduced it.
#       Fixed by switching both tests to `_UnconfiguredProviderClient`
#       (is_configured() -> False) for every chain entry, so
#       chain_has_configured_candidate is genuinely False and the resolver is
#       actually reached - NO change to preflight()/client.py itself, which
#       was already correctly wired. Verified for real (not just reasoned
#       about) by shimming a minimal `app.core.config.settings` object and
#       running the ACTUAL production `AIGateway.preflight()` against both the
#       fixed and the original fixture in this sandbox (no Docker needed,
#       since request_log.py's own persistence layer already no-ops safely
#       without sqlalchemy) - the fixed fixture passes both assertions
#       against the real code path; the original fixture reproduces
#       resolver.calls==[] / approval_required==False identically to the
#       CEO's own report, confirming the root cause was the test's fixture
#       choice, not the gateway's resolver wiring.
#   (2) Repeated (swallowed but noisy) ForeignKeyViolation logging during
#       AIRequestLog persistence, from three complete()-path tests
#       (test_injected_resolver_true_bypasses_gate_without_the_flag,
#       test_injected_resolver_false_still_raises_premium_approval_required,
#       test_resolver_receives_the_requests_own_company_profile_id_and_capability)
#       that passed `company_profile_id=str(uuid.uuid4())` - a syntactically
#       valid UUID that `_persist_ai_request_log()`'s own `_as_uuid()` parses
#       and attempts as a real `company_profiles.id` FK, which doesn't exist
#       for a random UUID. Fixed per the CEO's own second suggested option
#       ("avoiding fake company IDs in request logging tests"): the first two
#       tests don't need any particular company_profile_id for their
#       assertions, so it's dropped entirely (defaults to None, matching
#       every pre-existing test in this class); the third test genuinely
#       needs a concrete value to prove pass-through to the resolver, so it
#       now uses a deliberately NON-UUID string ("not-a-real-company-profile-id")
#       - `_as_uuid()` fails to parse it and substitutes None (no FK ever
#       attempted), while the FAKE resolver (which never validates UUID-ness,
#       it only records what it's given) still receives and records the exact
#       string, so the pass-through assertion is unweakened.
#
# This is "pre-authorization," explicitly NOT "pause/resume" - approving a
# flagged event grants a time-boxed window for the FLAGGED EVENT'S OWN
# (company_profile_id, capability) pair, not a resume of that literal
# request (AIRequestLog carries no reference back to whichever business
# object originated it - there is nothing to resume, and nothing to resume
# even if it were wanted). Reject is an audit annotation only - it changes
# nothing about the gate.
#
#   Backend:
#   - app/models/ai_premium_preauthorization.py (NEW): AIPremiumPreauthorization -
#     one row per Approve/Reject decision, never mutated once written
#     (append-only, matching AIProviderConfigAudit's own precedent).
#   - alembic/versions/0032_ai_premium_preauthorizations.py (NEW).
#   - app/core/config.py: AI_GATEWAY_PREMIUM_PREAUTH_MINUTES = 120.
#   - app/ai_gateway/premium_approval_resolver.py (NEW): PremiumApprovalResolver
#     ABC (one method, is_preauthorized()) + SQLAlchemyPremiumApprovalResolver,
#     the only concrete implementation today - opens its own short-lived
#     session, delegates the actual query to premium_preauthorization.py's
#     has_live_preauthorization() rather than duplicating it. Fails SAFE
#     (False) on any error or unparseable company_profile_id, never fails
#     open. Deliberately sqlalchemy-free at module-import time (only
#     abc/uuid/logging) - the DB layer is imported lazily inside the
#     concrete class's own method, same discipline client.py's own
#     _resolve_provider() already established.
#   - app/ai_gateway/premium_preauthorization.py (NEW): the existing-session
#     service layer (has_live_preauthorization/latest_decision_for/
#     grant_preauthorization/list_preauthorization_history) - used by BOTH
#     the resolver (a fresh session) and ui_query.py (an already-open
#     session), so "what counts as a live grant" exists in exactly one
#     place.
#   - app/ai_gateway/client.py: AIGateway gained an optional
#     `premium_approval_resolver` constructor param (same shape as
#     `provider_lookup`); complete()'s and preflight()'s gate checks now
#     also ask `_is_premium_preauthorized(request)` - only consulted AFTER
#     request.premium_approved, so the already-approved fast path never
#     pays for a resolver round trip it doesn't need.
#   - app/ai_gateway/ui_query.py: ApprovalRequestRead gained a computed
#     `status` field (_approval_status_for() - pending/approved/rejected,
#     an expired approval correctly reads as pending again); new
#     get_approval_request_log() (shared 404-translation lookup),
#     to_premium_preauthorization_read() (shared row conversion),
#     list_approval_history().
#   - app/schemas/ai_gateway.py: ApprovalRequestRead.status;
#     PremiumPreauthorizationRead (NEW).
#   - app/api/routes/ai_gateway.py: this router's second WRITE surface -
#     POST /ai-gateway/approvals/{id}/approve, POST .../reject, GET
#     .../approvals/history - all three admin-gated
#     (get_current_active_admin, CEO decision 3). GET /ai-gateway/approvals
#     itself is unchanged (any authenticated user, own companies only).
#
#   Frontend:
#   - ai-gateway/types.ts: ApprovalRequest.status (ApprovalStatus);
#     PremiumPreauthorization (NEW).
#   - ai-gateway/providers/GatewayDataProvider.ts (+ApiGatewayProvider.ts,
#     +MockGatewayProvider.ts): approveRequest()/rejectRequest()/
#     listApprovalHistory() added to the provider abstraction.
#     MockGatewayProvider's APPROVALS fixture gained a real, mutable
#     `status` field and an in-memory APPROVAL_HISTORY audit trail.
#   - ai-gateway/hooks/useApprovals.ts: approve()/reject() are now real
#     mutations (replacing the prior "not yet implemented" Toast stub);
#     both refresh() the full list afterward, since `status` is computed
#     server-side per (company, capability), not per literal row.
#   - ai-gateway/hooks/useApprovalHistory.ts (NEW): same read-only contract
#     convention as every other AI Gateway hook; `enabled` skips the fetch
#     for a non-admin caller (avoids a guaranteed-403 request).
#   - ai-gateway/components/ApprovalCard.tsx: shows a status Badge instead
#     of Approve/Reject buttons once a row is no longer "pending";
#     `canDecide` (client-side admin courtesy) gates the buttons.
#   - ai-gateway/components/ApprovalFilterBar.tsx (NEW): Pending/Approved/
#     Rejected/All segmented filter over the approvals list.
#   - ai-gateway/components/ApprovalHistoryTable.tsx (NEW): built on the
#     shared `Table` design-system primitive (Design Bible Section 4.6) -
#     no new one-off table markup.
#   - pages/ai-gateway/AIGatewayApprovals.tsx: replaced the toast stubs and
#     the History PlaceholderNotice with real mutations behind the shared
#     `ConfirmDialog` primitive (M8.17's Global Delete System precedent) and
#     a real Tabs-switched history table.
#   - pages/ai-gateway/AIGatewayOverview.tsx: its own Pending Premium
#     Approvals preview updated identically (real mutations, ConfirmDialog,
#     filtered to status === "pending" only).
#
# NOT implemented this step (explicitly out of scope per the approved
# plan): notification publishing on decision (CEO decision 4, deferred);
# company-owner approval permissions (CEO decision 3, admin-only); batch
# approval, org-level approval policies, spending limits, multiple-admin
# workflows, approval-history charts (all disclosed future work in the
# plan doc's own scalability review, Section 6).
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
echo "=== 2/6: migration - confirm 0032 (Step 7) is current ==="
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current

echo
echo "=== 3/6: this step's own new/extended test suites ==="
docker compose exec -T backend python -m unittest \
  tests.test_premium_approval_resolver_pure \
  tests.test_premium_approval_e2e \
  tests.test_ai_provider_hierarchy_e2e \
  -v

echo
echo "=== 4/6: FULL regression sweep ==="
docker compose exec -T backend python -m unittest \
  tests.test_ai_gateway_diagnostics_pure \
  tests.test_ai_gateway_ui_query_e2e \
  tests.test_ai_gateway_capabilities_pure \
  tests.test_routing_simulator_pure \
  tests.test_model_role_management_pure \
  tests.test_model_role_management_e2e \
  tests.test_local_model_policy_pure \
  tests.test_provider_config_pure \
  tests.test_provider_config_e2e \
  tests.test_ai_gateway_provider_management_pure \
  tests.test_provider_management_e2e \
  tests.test_ai_provider_hierarchy_pure \
  tests.test_ai_execution_platform_e2e \
  tests.test_supervisor_e2e \
  tests.test_supervisor_invocation_action_e2e \
  tests.test_llm_mapping_pure \
  tests.test_research_analysis_agent_pure \
  tests.test_research_analysis_agent_full_chain_e2e \
  tests.test_llm_analysis_engine_e2e \
  tests.test_analysis_engine_registry_e2e \
  tests.test_research_workflow_e2e \
  tests.test_outreach_workflow_e2e \
  tests.test_personalization_workflow_e2e \
  tests.test_pilot_workflow_e2e \
  tests.test_workflow_events \
  tests.test_event_dispatcher_worker \
  tests.test_step_runner_worker \
  tests.test_workflow_instance_models \
  tests.test_realtime_poller \
  tests.test_thread_builder \
  -v

echo
echo "=== 5/6: smoke test - approve/reject/history round trip over real HTTP ==="
echo "(manual checklist below covers this in full; automated route-function-level"
echo "coverage is in tests.test_premium_approval_e2e's TestApproveRejectRoutes /"
echo "TestApprovalHistoryRoute / TestGetCurrentActiveAdmin classes above)"

echo
echo "=== 6/6: frontend build ==="
docker compose exec -T frontend npx tsc -b --force || (cd frontend && npx tsc -b --force)
docker compose exec -T frontend npm run build || (cd frontend && npm run build)

echo
echo "ALL AUTOMATED CHECKS COMPLETE"
echo
echo "Genuinely executed in the authoring sandbox (no Docker/Postgres/network"
echo "access - confirmed by direct \`docker\` command-not-found and a direct"
echo "\`pip install\`/\`npm install\` 403 Forbidden attempt, same disclosed"
echo "limitation every prior M8.3 step's own verify script already notes):"
echo "  - py_compile ran clean across the ENTIRE backend tree (app/ + tests/ +"
echo "    alembic/), including every new/edited Step 7 file."
echo "  - tests.test_premium_approval_resolver_pure - 8 assertions, ALL genuinely"
echo "    executed for real (not just py_compile-checked): PremiumApprovalResolver"
echo "    ABC cannot be instantiated directly / a conforming fake subclass can;"
echo "    SQLAlchemyPremiumApprovalResolver.is_preauthorized() fails safe (False)"
echo "    for company_profile_id=None, empty string, a non-UUID string, AND a"
echo "    well-formed UUID that reaches (and fails safe past) the lazy DB-layer"
echo "    import in this sqlalchemy-free sandbox; get_premium_approval_resolver()"
echo "    returns a SQLAlchemyPremiumApprovalResolver singleton. This module has"
echo "    no top-level settings/sqlalchemy import (only abc/uuid/logging), unlike"
echo "    AIGateway itself, which is why this suite could run for real here while"
echo "    tests.test_ai_provider_hierarchy_e2e's own new resolver-injection tests"
echo "    could not run via \`python -m unittest\` (constructing AIGateway needs"
echo "    settings)."
echo "  - Full pre-existing pure suite re-run for regression: 239/239 pass, 2"
echo "    skipped (manual_csv's own sqlalchemy dependency, unrelated to this step,"
echo "    same skip every prior step's own run already reports)."
echo "  - CEO REVIEW FIX verification (2026-07-29): the ACTUAL production"
echo "    AIGateway.preflight()/complete() code was exercised directly in this"
echo "    sandbox by shimming sys.modules['app.core.config'] with a minimal fake"
echo "    settings object (request_log.py's own persistence layer already no-ops"
echo "    safely without sqlalchemy, so no DB shim was needed) - both fixed"
echo "    preflight tests now pass against the real code (resolver.calls==1,"
echo "    approval_required flips correctly with the resolver's return value in"
echo "    both directions); re-running the SAME real code against the ORIGINAL"
echo "    (bugged) fixture reproduces resolver.calls==[] / approval_required==False"
echo "    identically to the CEO's own report, confirming the root cause was the"
echo "    test fixture, not client.py's resolver wiring (client.py itself:"
echo "    zero lines changed by this fix); the three complete()-path fixes"
echo "    (dropped/replaced fake company_profile_id values) were verified the"
echo "    same way, plus a direct check that the replacement non-UUID string"
echo "    resolves to None in _as_uuid() (no FK insert would ever be attempted)."
echo "  - \`npx tsc -b --force\` ran clean (exit 0) across the entire frontend"
echo "    tree, including every new/edited Step 7 file (types.ts,"
echo "    GatewayDataProvider.ts, ApiGatewayProvider.ts, MockGatewayProvider.ts,"
echo "    useApprovals.ts, useApprovalHistory.ts, ApprovalCard.tsx,"
echo "    ApprovalFilterBar.tsx, ApprovalHistoryTable.tsx, AIGatewayApprovals.tsx,"
echo "    AIGatewayOverview.tsx)."
echo
echo "NOT run in the authoring sandbox - needs Docker, run for real above:"
echo "  - Migration 0032 itself (alembic upgrade head against a real Postgres)."
echo "  - tests.test_premium_approval_e2e (real-DB coverage: has_live_preauthorization()"
echo "    live/expired/wrong-capability/wrong-company/None-company scoping;"
echo "    SQLAlchemyPremiumApprovalResolver's real-DB branch; latest_decision_for()'s"
echo "    rejection-supersedes-approval ordering; grant_preauthorization()'s"
echo "    real-time expires_at computation using AI_GATEWAY_PREMIUM_PREAUTH_MINUTES,"
echo "    append-only writes, ValueError on an invalid decision string;"
echo "    list_preauthorization_history()'s scoping/ordering; ui_query.py's"
echo "    _approval_status_for()/list_approvals().status pending/approved/rejected/"
echo "    expired-reverts-to-pending transitions; get_approval_request_log()'s"
echo "    unknown-id/wrong-error-type/unowned-company/unattributed-row -> None"
echo "    guards; the three new routes' 404s, admin-gating (TestGetCurrentActiveAdmin,"
echo "    reusing the exact precedent test_provider_management_e2e.py already"
echo "    established), and full approve/reject/history round trips)."
echo "  - tests.test_ai_provider_hierarchy_e2e's new TestPremiumApprovalGate"
echo "    resolver-injection tests (injected-resolver-true bypasses the gate"
echo "    without the flag; injected-resolver-false still raises; the resolver"
echo "    receives the request's own company_profile_id/capability; the"
echo "    premium_approved flag short-circuits BEFORE the resolver is ever"
echo "    consulted - zero calls; preflight() honors the resolver both ways) -"
echo "    needs settings/sqlalchemy at AIGateway construction time."
echo "  - The full FULL regression sweep (every suite listed in step 4/6 above)."
echo "  - The actual \`npm run build\` bundling step (vite build) - this authoring"
echo "    sandbox's own @rollup/rollup-linux-arm64-gnu optional dependency is"
echo "    missing AND npm registry access is blocked (403 Forbidden, confirmed by"
echo "    a direct install attempt) - the SAME pre-existing environment limitation"
echo "    every prior M8.3 step's own verify script already discloses. \`npx tsc -b"
echo "    --force\` (above) was used as the closest in-sandbox proxy for the"
echo "    type-check half specifically."
echo
echo "Manual verification checklist (this is the only way to see the real UI/wiring):"
echo "-- (a) As an admin, trigger a premium-approval-required event (e.g. exhaust"
echo "--     local/free providers for a live capability with"
echo "--     AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL=true), open AI Gateway > Approvals"
echo "--     - confirm it appears in the Pending queue with correct feature,"
echo "--     company, provider, estimated cost, and waiting time."
echo "-- (b) Click Approve - confirm the ConfirmDialog explains this grants a"
echo "--     120-minute pre-authorization for the (company, capability) pair, NOT"
echo "--     a resume of this specific request; confirm the click; confirm a"
echo "--     success Toast, the card either disappears from the Pending filter or"
echo "--     shows an 'approved' badge, and the History tab now shows the decision"
echo "--     with the correct decided-by/decided-at/expires-at."
echo "-- (c) Re-submit the SAME (company, capability) request within the 120-minute"
echo "--     window with premium_approved unset - confirm it now completes"
echo "--     automatically (no PremiumApprovalRequiredError) via the gateway's own"
echo "--     preauthorization check, without the caller needing to pass"
echo "--     premium_approved=True itself."
echo "-- (d) Trigger a second, DIFFERENT approval-required event and click Reject -"
echo "--     confirm the ConfirmDialog explains this is an audit annotation only;"
echo "--     confirm nothing about routing changes (the gate remains armed for a"
echo "--     retry), and the row shows a 'rejected' badge / appears correctly under"
echo "--     the Rejected filter and in History."
echo "-- (e) As a NON-admin user, open AI Gateway > Approvals - confirm every row's"
echo "--     Approve/Reject buttons are replaced with 'Admin required to approve or"
echo "--     reject.', and the History tab shows 'Approval history is admin-only.'"
echo "--     instead of attempting (and 403ing on) the real fetch."
echo "-- (f) curl POST /api/v1/ai-gateway/approvals/{id}/approve and .../reject as a"
echo "--     non-admin - confirm 403 for both; as an admin with an unknown/wrong-"
echo "--     type id - confirm 404 for both."
echo "-- (g) curl GET /api/v1/ai-gateway/approvals/history as a non-admin - confirm"
echo "--     403; as an admin - confirm the JSON reflects every decision made in"
echo "--     (b)/(d) above, most-recent-first."
echo "-- (h) Confirm the AI Gateway Overview page's 'Pending Premium Approvals'"
echo "--     preview only ever shows status === pending rows (never an"
echo "--     already-decided one), and that approving/rejecting from THAT preview"
echo "--     (not just the full Approvals page) works identically."
echo
echo "Deferred, disclosed rather than silently dropped - see"
echo "docs/architecture/m8-3-ai-gateway-control-center-plan.md Section 13's own"
echo "scalability review for the full remaining build order:"
echo "  - Notification publishing on Approve/Reject decisions (CEO decision 4)."
echo "  - Company-owner approval permissions (CEO decision 3 - admin-only for now)."
echo "  - Batch approval, org-level approval policies, per-company spending limits,"
echo "    multiple-admin coordination, approval-history charts/trends."
