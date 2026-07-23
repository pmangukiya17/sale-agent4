# Comprehensive verification matrix — master checklist

**Status:** the master, single-source-of-truth checklist for this
platform's first Comprehensive Verification pass. Track A (static/
structural verification) is already complete — see
`deferred-items-and-design-boundaries.md` and this session's own Track A
findings summary for its results. This matrix covers what remains:
Track B1 and Track B2, the live verification that requires a real
Docker/Postgres/browser environment (outside this sandbox's
capabilities). Every row below is genuinely un-executed as of this
writing — nothing in this matrix has been run yet, so every status is
`Pending`.

Row detail (exact commands, prerequisites, pass/fail criteria, and the
full manual checklist) lives in
[`track-b1-live-verification.md`](./track-b1-live-verification.md); this
document is the tracking/status layer on top of it, not a replacement
for it.

**Track B2 note:** three areas are deliberately excluded from Track B1
and reserved for a separate pass after Track B1 completes, per the
CEO's own sequencing — they correspond to the three findings that drove
this session's architectural fixes (ProspectContact CASCADE, legacy
Company/Contact isolation, open registration), and get their own
dedicated re-verification rather than being folded into the general
sweep.

---

## Group 1 — Scripted milestones (existing `verify_*.sh`)

| # | Feature | Automated verification available | Manual verification required | Track | Status |
|---|---|---|---|---|---|
| 1 | M5 Layer 2 — migration 0008, fresh DB (`verify_0008.sh`) | Yes | No | B1 | Pending |
| 2 | M5 Layer 3 — Delivery Engine Core (`verify_layer3.sh`) | Yes | No | B1 | Pending |
| 3 | M5 Layer 4 — Schemas (`verify_layer4.sh`) | Yes | No | B1 | Pending |
| 4 | M5 Layer 5 — API routes, live HTTP (`verify_layer5.sh`) | Yes | No | B1 | Pending |
| 5 | M5 Layer 6 — Frontend build (`verify_layer6.sh`) | Yes | No | B1 | Pending |
| 6 | M5 Layer 7 — Full-stack integration (`verify_layer7.sh`) | Yes | No | B1 | Pending |
| 7 | M6.1 — Conversation/EmailMessage schema (`verify_m6_1.sh`) | Yes | No | B1 | Pending |
| 8 | M6.2 — Mailbox Sync (`verify_m6_2.sh`) | Yes | No | B1 | Pending |
| 9 | M6.3 — Thread Builder (`verify_m6_3.sh`) | Yes | No | B1 | Pending |
| 10 | M6.4 — Reply Intelligence (`verify_m6_4.sh`) | Yes | No | B1 | Pending |
| 11 | M7.1 Part 1 — Event Infra/Workflow Engine core (`verify_m7_1_part1.sh`) | Yes | No | B1 | Pending |
| 12 | M7.1 Part 2 — pilot workflow execution (`verify_m7_1_part2.sh`) | Yes | No | B1 | Pending |
| 13 | M7.2 — AI Gateway/Prompt Builder/Agent Runtime (`verify_m7_2.sh`) | Yes | No | B1 | Pending |
| 14 | M7.3 — Supervisor/Orchestrator (`verify_m7_3.sh`) | Yes | No | B1 | Pending |
| 15 | M7.4 — Autonomous Multi-Agent Workflows (`verify_m7_4.sh`) | Yes | No | B1 | Pending |
| 16 | M8.5 — Event Backbone & Notification Center (`verify_m8_5.sh`) | Yes | No | B1 | Pending |
| 17 | M8.6 — Real-Time Event Streaming (`verify_m8_6.sh`) | Yes | No | B1 | Pending |

## Group 2 — Manual verification, no script exists (Track B1)

Everything from M8.7 onward has no `verify_*.sh` coverage today — this
is the Priority 3 "verification coverage gap" Track A flagged, tracked
separately from this checklist (writing real scripts for this range is
a future step, not part of this matrix).

| # | Feature | Automated verification available | Manual verification required | Track | Status |
|---|---|---|---|---|---|
| 18 | Command Center dashboard — loads, all zones render, no console errors | No | Yes | B1 | Pending |
| 19 | World Map (M8.16) — clickable country paths, hover tooltip (name + count), honest no-data state | No | Yes | B1 | Pending |
| 20 | Workflow Engine wiring — Discovery live execution view reaches a terminal state | No | Yes | B1 | Pending |
| 21 | Workflow Engine wiring — Research live execution view (M8.13) reaches a terminal state | No | Yes | B1 | Pending |
| 22 | Workflow Engine wiring — Personalization live execution view (M8.14) reaches a terminal state | No | Yes | B1 | Pending |
| 23 | Workflow Engine wiring — Outreach live execution view (M8.15) reaches a terminal state | No | Yes | B1 | Pending |
| 24 | Analytics page (M8.9) — renders real aggregated data | No | Yes | B1 | Pending |
| 25 | Reports page (M8.9) — list→detail run history browser | No | Yes | B1 | Pending |
| 26 | Conversations UI (M6.5) — lists real conversations | No | Yes | B1 | Pending |
| 27 | CRM Automation Recommended Actions panel (M6.6) — reflects a real Task row | No | Yes | B1 | Pending |
| 28 | Global Delete System (M8.17) — Company Products / Knowledge Base / Sending Profiles delete flow | No | Yes | B1 | Pending |
| 29 | Global Delete System (M8.17) — Outreach Playbook version delete + RESTRICT conflict returns clean error | No | Yes | B1 | Pending |
| 30 | Discovery Search RESTRICT fix (migration 0023) — direct-API spot check on a search with real Job/Run history | No | Yes | B1 | Pending |
| 31 | Legacy Company/Contact Phase 1 — Sidebar "Legacy" badge on both Pipeline and Contacts | No | Yes | B1 | Pending |
| 32 | Legacy Company/Contact Phase 1 — Contacts page shows `TransitionalBanner` | No | Yes | B1 | Pending |
| 33 | Legacy Company/Contact Phase 1 — `/companies`/`/contacts` marked deprecated in Swagger UI | No | Yes | B1 | Pending |
| 34 | Notifications/Realtime — triggered event appears in Notification Center without manual refresh | No | Yes | B1 | Pending |

## Group 3 — Reserved for Track B2 (out of scope for B1)

`tests/test_track_b2_verification.py` + `verify_track_b2.sh` (added after
Track B1's own hand-off) now give all three of these real automated
coverage — direct route-function calls against a real DB, the same
convention as every other `*_e2e.py` test in this suite — so "Automated
verification available" moves from No to Yes for all three rows below.
This does NOT flip `Status` to done: the suite still needs to actually
run against real Postgres (no Docker/Postgres access in the authoring
sandbox — see that test file's own docstring), so all three stay
`Pending` until `verify_track_b2.sh` is actually executed.

| # | Feature | Automated verification available | Manual verification required | Track | Status |
|---|---|---|---|---|---|
| 35 | ProspectContact delete/archive behavior — RESTRICT-protected hard delete, archive/unarchive routes, default-hide-archived list filter | Yes | No | B2 | Pending |
| 36 | Multi-business isolation — legacy Company/Contact tenant-scoping re-check | Yes | No | B2 | Pending |
| 37 | Authentication registration flow — admin gate, bootstrap exception fires exactly once on a fresh DB, second registration without admin token 403s | Yes (with one caveat — see below) | No | B2 | Pending |

**Row 37 caveat, surfaced while writing the test:** the bootstrap-exception
branch is realistically unreachable via the live API in any normally-booted
deployment — `app.main.ensure_first_admin()` runs during FastAPI's startup
lifespan and seeds a real admin before the server accepts its first
request, so `is_bootstrap` is already permanently `False` by the time any
client could call `POST /auth/register`. `TestAuthRegistrationBootstrapException`
exercises the branch directly by calling `register()` itself, bypassing
`ensure_first_admin()` — genuine, correct coverage of the code path, but
not something `verify_track_b2.sh` running against an already-booted
`docker compose up` container will ever observe as live behavior (those two
tests are expected to self-`SKIP` there, with an explicit message — see
the script's own header). This isn't a gap in the verification; it's a
real characteristic of the interim design worth the CEO knowing about.

---

## Group 4 — Track C (new capability delivery, not re-verification)

Unlike Groups 1-3 (all re-verifying already-shipped M0-M8 work), Track C
rows are net-new capability delivery per
[`dashboard-capabilities-architecture-plan.md`](./dashboard-capabilities-architecture-plan.md)
(approved architecture, implementation in progress). Added here rather
than a separate matrix so "is everything this project has shipped
actually verified" stays answerable from one place. Each row gets its own
`verify_track_cN.sh` at the repo root, same conventions as Group 1's
scripts.

| # | Feature | Automated verification available | Manual verification required | Track | Status |
|---|---|---|---|---|---|
| 38 | Open Conversations KPI — count endpoint tenant-isolated, status-filtered, zero-conversations edge case (`verify_track_c1.sh`) | Yes | Yes (visual: real number + breathing glow on count > 0) | C1 | Pass |
| 39 | AI Recommendations — cross-portfolio endpoint tenant-isolated, status filter, limit, empty-portfolio edge case (`verify_track_c2.sh`) | Yes | Yes (visual: real recommendation rows + breathing glow on recommendations > 0) | C2 | Pass |
| 40 | Opportunity domain — migration applied, pure state-machine unit tests (stage skipping/no-op rejection), route ordering, CRUD/stage-transition/tenant-isolation/history-tracking/edge-case real-DB tests (`verify_track_c3.sh`) | Yes | No (no frontend surface in this track - see Track C4) | C3 | Pass |
| 41 | Sales Pipeline / Pipeline Overview / Revenue Pipeline — funnel conversion-rate math, per-currency revenue breakdown, empty-pipeline edge case, tenant isolation (`verify_track_c4.sh`) | Yes | Yes (visual: stage boxes, conversion %s, and KPI value all real; breathing glow on real Opportunity activity) | C4 | Pending |

---

## Summary

- **41 total verification areas.**
- **24 automated** (Group 1's 17 existing scripts + Group 3's 3 rows,
  covered by `test_track_b2_verification.py`/`verify_track_b2.sh`, +
  Group 4's row 38, covered by `test_open_conversations_count.py`/
  `verify_track_c1.sh`, + Group 4's row 39, covered by
  `test_ai_recommendations_portfolio.py`/`verify_track_c2.sh`, + Group 4's
  row 40, covered by `test_opportunity_state_machine.py`/
  `test_opportunities_e2e.py`/`verify_track_c3.sh`, + Group 4's row 41,
  covered by `test_pipeline_dashboard_metrics.py`/`verify_track_c4.sh`) +
  **20 manual** (Group 2's 17 + Group 4's 3 visual checks - row 40 has no
  visual check, since Track C3 has no frontend surface of its own).
- **34 areas in Track B1**, **3 areas in Track B2**, **1 area in Track C1**,
  **1 area in Track C2**, **1 area in Track C3**, **1 area in Track C4**
  (more Track C rows will be added as C5 lands).
- **3 executed (row 38, Track C1; row 39, Track C2; row 40, Track C3 —
  all `Pass`, confirmed by the CEO against a real Docker/Postgres/browser
  run). 38 rows remain `Pending`, including row 41 (Track C4) pending the
  same real Docker/Postgres/browser run.**

This matrix should be updated in place as each row executes — mark each
`Status` as `Pass`, `Fail`, or `Skipped` (with a one-line reason) rather
than editing this document's structure. Do not consider the
Comprehensive Verification pass closed until every row has a non-Pending
status, and every `Fail` has either been fixed and re-verified or
explicitly accepted as a known limitation with the same discipline
`deferred-items-and-design-boundaries.md` already uses.
