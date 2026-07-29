#!/usr/bin/env bash
# M8.3 - AI Gateway Management & Control, STEP 6 ONLY (Gateway Diagnostics)
#
# Builds on Steps 1-5 (Provider Config, Provider Management UI, Model Role
# Management, Routing Simulator, Provider Capability Viewer - all approved,
# verified, committed separately). Step 6 is READ-ONLY end to end: it
# EXPLAINS the Gateway's current health, it never fixes anything and never
# actions a finding. Per the CEO's explicit Step 6 requirements
# (2026-07-28): preserve the existing architecture; build diagnostics from
# existing gateway telemetry rather than duplicating logic; surface
# configuration issues, routing failures, provider health, and actionable
# recommendations; clearly separate warnings from errors; keep diagnostics
# read-only.
#
# CEO REVIEW FIX (2026-07-28, first submission rejected): the reported
# failure in tests.test_ai_gateway_ui_query_e2e's
# test_premium_approval_required_row_is_excluded_from_failure_findings was
# root-caused to the TEST's own assertion shape, not a logic bug in
# get_diagnostics()/build_diagnostics() - code review confirmed the SQL
# exclusion (`AIRequestLog.error_type != _PREMIUM_APPROVAL_ERROR_TYPE`) and
# the pure severity mapping ("waiting" routing outcome -> "info", never
# "error") were both already correct. The ORIGINAL test asserted the
# recent-failures query's ENTIRE global findings list contained no
# "...time(s)..." title - but that query is deliberately GLOBAL/unscoped
# (see get_diagnostics()'s own docstring), so any pre-existing, unrelated
# failure row already in this shared Docker/Postgres database (from a
# prior manual pass, another test, or real usage) could independently make
# that "must be globally empty" assertion fail, with zero connection to
# the approval-exclusion logic actually being tested. Fixed by: (1)
# extracting a single `_PREMIUM_APPROVAL_ERROR_TYPE` constant in
# ui_query.py, reused by `_status_of()`/`_chain_summary()`/
# `list_approvals()`/`get_diagnostics()` so there is exactly one place
# this exclusion could ever drift, and (2) rewriting every e2e test in
# `TestGatewayDiagnostics` to be immune to pre-existing DB noise - either a
# BEFORE/AFTER delta on the exact error/warning/info counts (so any
# pre-existing finding contributes equally to both sides and cancels out
# of the comparison), or a synthetic `provider_key` value
# (`__diag_test_provider__`) that cannot collide with anything real
# production code would ever write. A new test,
# `test_premium_approval_required_row_remains_visible_in_approvals`, now
# proves in one place that the SAME inserted row is fully visible via
# `list_approvals()` while simultaneously excluded from
# `get_diagnostics()`'s failure findings - directly the CEO's own "remains
# visible in approval-related views" + "does not increase failure counts"
# checklist. No change was needed to diagnostics.py's pure severity logic
# itself; tests.test_ai_gateway_diagnostics_pure's existing 17 assertions
# (unchanged) already cover severity calculation correctness end to end.
#
#   Backend:
#   - app/ai_gateway/diagnostics.py (NEW) - pure module (no settings/
#     sqlalchemy import at module level, same discipline routing_simulator.py/
#     capabilities.py/tiers.py already established). `build_diagnostics()`
#     takes already-resolved facts (ProviderHealthInput/RoutingOutcomeInput/
#     FailureSummaryInput - each one lifted directly from an EXISTING
#     function's own output, never recomputed) and decides what's worth
#     surfacing, with what severity ("error" | "warning" | "info" - the
#     CEO's own "clearly separate warnings from errors" requirement) and
#     what recommendation. Covers three categories: provider_health
#     (enabled-but-unconfigured / intentionally-disabled), configuration
#     (AI_MODE has no eligible provider at all, premium approval required
#     but nothing to approve into), and routing (the SAME live routing
#     preview GET /ai-gateway/routing already computes, plus observed
#     AIRequestLog failures in the last 24 hours).
#   - app/ai_gateway/ui_query.py: get_diagnostics() - the impure glue,
#     wiring get_provider_config()/is_configured()/tier_of()/
#     list_routing_decisions() (all EXISTING functions, reused verbatim)
#     plus one new grouped AIRequestLog query (global, not user-scoped -
#     same reasoning ProviderSummaryRead's own docstring already gives for
#     provider-level stats being instance-wide infrastructure) into
#     build_diagnostics().
#   - app/schemas/ai_gateway.py: DiagnosticFindingRead / GatewayDiagnosticsRead.
#   - app/api/routes/ai_gateway.py: GET /ai-gateway/diagnostics - ADMIN-
#     GATED (get_current_active_admin), same precedent as Provider
#     Management's config routes and Model Role Management - a heavier
#     trust level than GET /ai-gateway/providers or GET
#     /ai-gateway/capabilities, since this endpoint reveals cross-user
#     aggregate failure data and each provider's admin-set enabled state.
#
#   Frontend:
#   - ai-gateway/types.ts: DiagnosticFinding / DiagnosticSeverity /
#     GatewayDiagnostics (mirrors the backend schemas field-for-field).
#   - ai-gateway/providers/GatewayDataProvider.ts (+ApiGatewayProvider.ts,
#     +MockGatewayProvider.ts): getDiagnostics() added to the provider
#     abstraction. MockGatewayProvider's fixture is kept internally
#     consistent with its own pre-existing PROVIDERS/GATEWAY_SETTINGS/
#     ROUTING_DECISIONS fixtures (same two "not_configured" providers,
#     same "waiting" routing outcome for outreach_email_generation).
#   - ai-gateway/hooks/useGatewayDiagnostics.ts (NEW): auto-fetch-on-mount
#     hook, same contract as useProviderCapabilities.ts.
#   - ai-gateway/components/GatewayDiagnosticsPanel.tsx (NEW): findings
#     grouped into three clearly separate sections (Errors, Warnings, Info)
#     each with its own icon/tone, a summary badge row, a manual refresh
#     button, and an explicit "No issues detected" empty state - no
#     resolve/dismiss action anywhere on the panel, since there is nothing
#     to action against.
#   - pages/ai-gateway/AIGatewayHealth.tsx: wires the panel in below
#     Provider Capabilities; the trailing PlaceholderNotice is narrowed to
#     only the pieces still genuinely unimplemented (failover event
#     history and routing statistics CHARTS - distinct from the diagnostic
#     findings this step now delivers).
#
# NOT implemented this step (see Section 11's remaining build order):
# Premium Approval pre-authorization UI - Step 7. Failover event history
# and routing statistics as historical charts remain out of scope (this
# step surfaces CURRENT diagnostic findings, not a time-series view).
#
# CEO REVIEW FIX #2 (2026-07-28, second submission rejected): the Step 6
# suite itself passed clean (39/39), but the FULL regression sweep failed
# in an unrelated file - tests.test_research_workflow_e2e's
# test_research_request_run_flows_through_full_workflow_pipeline threw
# `ForeignKeyViolation: notification_dispatches.event_id still references
# events.id` during tearDown. Per the CEO's explicit instruction, this was
# NOT patched by silencing the test - the domain ownership model was
# determined first: NotificationDispatch.event_id and Notification.event_id
# both use `ondelete="RESTRICT"` to events.id (see app/models/notification.py's
# own docstrings), deliberately, per this project's standing "archive-over-
# delete / RESTRICT-not-CASCADE" convention (the same one migration "fix 7
# CASCADE FKs to RESTRICT" established earlier in Track A). NotificationDispatch
# is an INDEPENDENT consumer of Event, not a dependent child - so CASCADE
# would be the wrong fix. The real bug was pre-existing, incomplete test
# teardown ordering: this project runs REAL, always-on background worker
# containers (event_dispatcher_worker, step_runner_worker, a notification
# worker) that poll and consume `events` rows independently of any single
# test's own explicit tick calls. A bare `DELETE FROM events` in a test's
# tearDown races the live notification worker, which can insert a
# NotificationDispatch/Notification row referencing that test's own Event at
# any point after it was committed - test_research_workflow_e2e.py's own
# tearDown only cleaned up EventConsumption before deleting Event, missing
# Notification/NotificationDispatch entirely. Fixed using this project's own
# pre-existing, canonical helper - tests/event_backbone_cleanup.py's
# delete_events_and_dependents() (already used correctly by
# test_discovery_workflow_e2e.py) - which deletes EventConsumption,
# NotificationDispatch, and Notification (the complete set of live FKs to
# events.id) before the Event delete itself. Applied not just to the
# CEO-reported file but proactively (grep + a dispatched audit subagent) to
# every other test file with the identical latent bug: test_research_workflow_e2e.py,
# test_outreach_workflow_e2e.py, test_personalization_workflow_e2e.py,
# test_pilot_workflow_e2e.py, test_workflow_events.py,
# test_event_dispatcher_worker.py, test_step_runner_worker.py,
# test_workflow_instance_models.py, test_realtime_poller.py, and
# test_thread_builder.py (9 files total - test_thread_builder.py was the
# highest-risk of these, since it publishes real conversation.created
# events, exactly the event type the production Notification rule matches,
# and its own prior tearDown comment only reasoned about EventConsumption/
# the dispatcher, missing the live notification worker race entirely).
# tests/test_notifications.py was audited and confirmed already safe (its
# own tearDown already deletes NotificationDispatch/Notification by hand
# before Event, equivalent protection). No schema change, no CASCADE, no
# test-assertion weakening - the RESTRICT FK is confirmed as intentional,
# correct, unchanged.
#
# CEO REVIEW FIX #2b (2026-07-28, third submission rejected): after fix #2
# above, tests.test_realtime_poller's test_poll_once_fans_out_a_new_event_to_
# the_right_subscriber / test_poll_once_does_not_redispatch_the_same_event_
# twice still hung on `asyncio.wait_for(queue.get(), timeout=2)`. The
# initial hypothesis (a leaked-fixture Event backlog from the pre-fix #2
# ForeignKeyViolation race) was tested via a dedicated one-time purge
# script (backend/scripts/purge_orphaned_test_fixture_events.py - 8
# orphaned CompanyProfiles found and purged) and DISPROVEN: the exact same
# two tests still hung identically afterward, with Step 6's own suite and
# the pre-existing full regression sweep both still fully green (39/39,
# 223/223) - proving the ownership fix itself was never the cause. Further
# investigation traced the REAL root cause to app/realtime/poller.py's own
# `_fetch_new_events_sync()`: when `last_seen is None` (no watermark
# established yet - the exact state test_realtime_poller.py's own setUp/
# tearDown deliberately force, for test isolation, via
# `poller._last_seen_sequence_no = None`), the query was
# `ORDER BY sequence_no ASC LIMIT REALTIME_STREAM_POLL_BATCH_SIZE` (200)
# with NO lower bound - i.e. "the OLDEST 200 rows in the ENTIRE events
# table's history", not "whatever is new". That only ever worked by
# coincidence, for as long as this shared, long-lived dev Postgres
# database's `events` table happened to hold fewer than 200 total rows
# system-wide; once real, multi-milestone project history pushed that
# table past 200 rows (unrelated to any one fix - ordinary growth over
# this project's life), a freshly-published event could no longer be
# within the oldest-200 window and would never be fetched, so the
# subscriber's queue never received anything and `queue.get()` timed out.
# Confirmed via `git diff` that this exact code (and all of poller.py) had
# ZERO changes from fix #2/#2's-purge-script - this was a genuine, latent,
# pre-existing bug in the poller itself, invisible until now because this
# verify script never included test_realtime_poller.py in its own
# regression sweep before this review round. In real production this
# branch is essentially unreachable - `_run_forever()` always calls
# `_initialize_watermark()` (MAX(sequence_no)) before the poll loop
# starts, so `last_seen` is only ever None here on a genuinely EMPTY
# `events` table, where the fix below is behaviorally identical to the old
# code (both return nothing). Fixed IN THE POLLER ITSELF (per the CEO's
# explicit direction NOT to touch the tests): `_fetch_new_events_sync()`
# now branches on `last_seen is None` and fetches the NEWEST batch
# (`ORDER BY sequence_no DESC LIMIT 200`, reversed back to ascending
# before returning) instead of the oldest - guaranteeing a just-published
# event is always included regardless of how much older history exists,
# while preserving `poll_once()`'s existing "dispatch on the very first
# call" contract the tests rely on. Verified against a pure-Python
# simulation (5,000 unrelated historical events + 1 fresh event for the
# subscribed company) before editing anything for real - the old logic
# fails that simulation exactly as reported (fresh event never appears in
# the subscriber's queue), the new logic passes it. No test file touched;
# no data purge needed going forward (the one already run remains valid,
# harmless hygiene, just not what fixed this specific failure).
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
echo "=== 2/6: no new migration this step - confirm 0031 (Step 3) is still current ==="
docker compose exec -T backend alembic current

echo
echo "=== 3/6: this step's own new/extended test suites ==="
docker compose exec -T backend python -m unittest \
  tests.test_ai_gateway_diagnostics_pure \
  tests.test_ai_gateway_ui_query_e2e \
  -v

echo
echo "=== 4/6: FULL regression sweep ==="
docker compose exec -T backend python -m unittest \
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
  tests.test_ai_provider_hierarchy_e2e \
  tests.test_ai_execution_platform_e2e \
  tests.test_supervisor_e2e \
  tests.test_supervisor_invocation_action_e2e \
  tests.test_llm_mapping_pure \
  tests.test_research_analysis_agent_pure \
  tests.test_research_analysis_agent_full_chain_e2e \
  tests.test_llm_analysis_engine_e2e \
  tests.test_analysis_engine_registry_e2e \
  tests.test_research_workflow_e2e \
  -v

echo
echo "NOTE: tests.test_realtime_poller's two poll_once() tests previously hung"
echo "on asyncio.wait_for(queue.get()) - root-caused to a real, latent bug in"
echo "app/realtime/poller.py's own _fetch_new_events_sync() (oldest-N-in-all-"
echo "of-history query when last_seen is None), now fixed directly in the"
echo "poller itself - see CEO REVIEW FIX #2b's own header comment for the full"
echo "writeup. backend/scripts/purge_orphaned_test_fixture_events.py remains"
echo "available as safe, idempotent, disposable-fixture-only hygiene, but is no"
echo "longer required for these two tests specifically."
echo
echo "=== 5/6: CEO review fix #2 - event/notification teardown race, all 9 touched files ==="
docker compose exec -T backend python -m unittest \
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
echo "=== 6/6: frontend build ==="
docker compose exec -T frontend npx tsc -b --force || (cd frontend && npx tsc -b --force)
docker compose exec -T frontend npm run build || (cd frontend && npm run build)

echo
echo "ALL AUTOMATED CHECKS COMPLETE"
echo
echo "Genuinely executed in the authoring sandbox (no Docker/network access to"
echo "install sqlalchemy, pydantic, pydantic_settings, anthropic, openai, or"
echo "google-genai - confirmed by direct import attempts):"
echo "tests.test_ai_gateway_diagnostics_pure - 17 assertions total, all new this"
echo "step (provider-health severity assignment [disabled=info, enabled-but-"
echo "unconfigured=warning, disabled takes precedence over unconfigured for the"
echo "same provider], AI_MODE/provider-tier configuration checks [local_only /"
echo "premium_only with nothing eligible = error, premium approval required with"
echo "no premium configured = warning, correctly NOT flagged under local_only],"
echo "live routing-outcome mapping [success = no finding, failed = error, waiting"
echo "= info], observed-failure severity escalation [below threshold = warning, at"
echo "or above threshold = error, singular/plural wording], and a fully-healthy"
echo "gateway producing exactly zero findings) - genuinely pure, zero third-party"
echo "imports, since diagnostics.py never imports settings or sqlalchemy at module"
echo "level. Also re-ran the full pre-existing tests.test_ai_gateway_capabilities_pure,"
echo "tests.test_routing_simulator_pure, tests.test_model_role_management_pure,"
echo "tests.test_local_model_policy_pure, tests.test_provider_config_pure,"
echo "tests.test_ai_gateway_provider_management_pure, and tests.test_ai_provider_hierarchy_pure"
echo "suites for regression (124 assertions total across all pure suites, all"
echo "pass, confirming Step 6 added one new pure module without touching any"
echo "existing pure-testable behavior). py_compile ran clean across the ENTIRE"
echo "backend tree (app/ + tests/), including all 9 files touched by CEO review"
echo "fix #2 below. \`npx tsc -b --force\` ran clean (exit 0)"
echo "across the entire frontend tree, including the new types.ts/"
echo "GatewayDataProvider.ts/ApiGatewayProvider.ts/MockGatewayProvider.ts/"
echo "useGatewayDiagnostics.ts/GatewayDiagnosticsPanel.tsx/AIGatewayHealth.tsx"
echo "changes."
echo
echo "CEO review fix #2 (event/notification teardown race) - also ran the full"
echo "non-DB unit test suite (python -m unittest discover -s tests -p"
echo "'test_*.py') in the authoring sandbox: 436 tests collected, 393 pass, 0"
echo "genuine failures, 2 skipped, 43 collection errors - every one of the 43 is"
echo "a ModuleNotFoundError for sqlalchemy/fastapi (not installed in this"
echo "offline sandbox, no network access to pip install - confirmed by a direct"
echo "install attempt returning 403 Forbidden), not a test failure. This"
echo "confirms the 9 teardown edits introduced no syntax/import errors and did"
echo "not regress anything reachable without a live Postgres connection. The 9"
echo "files' own DB-backed test bodies (step 5/6 below) still need the real"
echo "Docker run to prove the ForeignKeyViolation is actually gone end to end -"
echo "same disclosed limitation as every other DB-backed suite in this script."
echo
echo "NOT run in the authoring sandbox - needs Docker, run for real above:"
echo "tests.test_ai_gateway_ui_query_e2e's TestGatewayDiagnostics class (6"
echo "assertions, REVISED per the CEO's Step 6 review fix - see this script's"
echo "own header for the full root-cause writeup): generated_at is a fresh"
echo "timestamp bounded by the call itself; error/warning/info counts match the"
echo "findings list exactly; a genuine execution failure (synthetic provider_key,"
echo "immune to any pre-existing DB noise) surfaces as exactly one routing finding"
echo "with correct wording AND contributes to the warning count; a"
echo "PremiumApprovalRequiredError row changes NONE of the error/warning/info"
echo "counts (before/after delta, not an absolute 'must be empty' check) and no"
echo "finding's detail ever mentions that error_type; that SAME approval-required"
echo "row remains fully visible via list_approvals() in the same test that proves"
echo "its diagnostics exclusion; and a failure outside the 24-hour lookback window"
echo "changes none of the counts either - needs sqlalchemy/a real DB session, same"
echo "reason importing app.ai_gateway.ui_query needs Docker for every other test"
echo "in that file."
echo "Also NOT run here: the actual full \`npm run build\` bundling step (vite"
echo "build, the second half of \`npm run build\` after \`tsc -b\`) - this"
echo "authoring sandbox's own @rollup/rollup-linux-arm64-gnu optional-dependency"
echo "is missing AND its npm registry access is blocked (403 Forbidden on a"
echo "direct install attempt), a pre-existing environment limitation unrelated"
echo "to any code in this step - confirmed by directly attempting \`npm run"
echo "build\` here: \`tsc -b\` (the type-check half) exits 0 clean, then \`vite"
echo "build\` itself fails to even start with a MODULE_NOT_FOUND on the native"
echo "rollup binary. This is the SAME disclosed limitation every prior"
echo "milestone's own verify script already notes; \`npx tsc -b --force\` was"
echo "used here as the closest in-sandbox proxy for the type-check portion"
echo "specifically. The Docker verify run above (step 5) uses a correctly-"
echo "provisioned Linux image with unrestricted npm access and does NOT hit"
echo "this limitation - THAT run is what actually confirms \`npm run build\`"
echo "succeeds end to end, including the vite bundle step this sandbox cannot"
echo "execute."
echo
echo "Manual verification checklist (this is the only way to see the real UI/wiring):"
echo "-- (a) As an admin, open AI Gateway > Health - confirm the 'Gateway"
echo "--     Diagnostics' card renders below Provider Capabilities, with"
echo "--     error/warning/info summary badges matching the findings actually"
echo "--     listed below them."
echo "-- (b) Confirm findings render in three clearly separate, labeled sections"
echo "--     (Errors, Warnings, Info) - never mixed into one undifferentiated"
echo "--     list - and that each finding shows a title, a detail sentence, and"
echo "--     an explicit recommendation."
echo "-- (c) Disable a configured provider in Provider Management, reload the"
echo "--     Health page - confirm a new 'X is disabled' info finding appears"
echo "--     for it, then re-enable it and confirm the finding disappears on"
echo "--     refresh."
echo "-- (d) Temporarily set AI_MODE=local_only via a provider override in"
echo "--     Provider Management such that no local provider is configured (or"
echo "--     via a real .env change + restart) - confirm an ERROR-severity"
echo "--     'AI mode is local_only but no local provider is configured' finding"
echo "--     appears; revert and confirm it disappears."
echo "-- (e) curl GET /api/v1/ai-gateway/diagnostics as a non-admin user - confirm"
echo "--     403, matching the panel's own 'requires an admin account' fallback."
echo "-- (f) curl GET /api/v1/ai-gateway/diagnostics as an admin - confirm the"
echo "--     JSON response's error_count/warning_count/info_count exactly match"
echo "--     len(findings) grouped by severity."
echo "-- (g) With a fully healthy gateway (every provider configured or"
echo "--     intentionally disabled, every live capability routes successfully,"
echo "--     no recent failures), confirm the panel shows the explicit 'No"
echo "--     issues detected' empty state rather than an empty list with no"
echo "--     explanation."
echo
echo "Deferred, disclosed rather than silently dropped - see"
echo "docs/architecture/m8-3-ai-gateway-control-center-plan.md Section 11 for the"
echo "full remaining build order:"
echo "  - Premium Approval pre-authorization UI - Step 7."
echo "  - Failover event history and routing statistics as historical, time-series"
echo "    charts - this step surfaces CURRENT diagnostic findings only, not a"
echo "    trend view."
