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

| # | Feature | Automated verification available | Manual verification required | Track | Status |
|---|---|---|---|---|---|
| 35 | ProspectContact delete/archive behavior — RESTRICT-protected hard delete, archive/unarchive routes, default-hide-archived list filter | No | Yes | B2 | Pending |
| 36 | Multi-business isolation — legacy Company/Contact tenant-scoping re-check | No | Yes | B2 | Pending |
| 37 | Authentication registration flow — admin gate, bootstrap exception fires exactly once on a fresh DB, second registration without admin token 403s | No | Yes | B2 | Pending |

---

## Summary

- **37 total verification areas.**
- **17 automated** (Group 1, existing scripts) + **20 manual** (Groups 2
  and 3 combined).
- **34 areas in Track B1**, **3 areas in Track B2**.
- **0 executed. All 37 rows are `Pending`.**

This matrix should be updated in place as each row executes — mark each
`Status` as `Pass`, `Fail`, or `Skipped` (with a one-line reason) rather
than editing this document's structure. Do not consider the
Comprehensive Verification pass closed until every row has a non-Pending
status, and every `Fail` has either been fixed and re-verified or
explicitly accepted as a known limitation with the same discipline
`deferred-items-and-design-boundaries.md` already uses.
