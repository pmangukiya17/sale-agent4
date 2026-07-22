# Track B1 — live verification execution package

**Status:** this document did not previously exist as a saved file. A
Track B preparation package (execution order, prerequisites, commands,
expected results, pass/fail criteria, manual UI checklist) was discussed
and approved earlier in the platform's first Comprehensive Verification
pass, but was only ever presented in chat and was never committed to the
repo — it is not recoverable from git history. This document rebuilds it
from scratch, grounded in the actual current `docker-compose.yml`, the
actual `verify_*.sh` scripts that exist today, and the state of the
platform after the three architectural fixes (execution-history RESTRICT
migrations, ProspectContact archive lifecycle, legacy Company/Contact
Phase 1 deprecation, interim admin-gated registration) that Track A's
findings led to.

**Why Claude cannot execute this itself:** this sandbox has no Docker,
no Postgres, and no browser — a standing, previously-disclosed
limitation, not new to this document. Everything below must be run by
the CEO (or whoever operates the real deployment) in an environment with
Docker Compose and a browser.

**Scope — this is B1, not B2.** Per the CEO's own sequencing: B1 covers
everything *unaffected* by the three architectural findings from Track A
(ProspectContact CASCADE, legacy Company/Contact multi-business
isolation, open user registration). B2 — re-verifying those three areas
specifically now that the fixes have shipped — is a separate, deliberate
next step, not folded into this document. Do not use this checklist as
confirmation that the fixes themselves work; B2 is what confirms that.

---

## Prerequisites

- Docker and Docker Compose v2 (`docker compose`, not the standalone
  `docker-compose`) installed and running.
- Ports 5433 (Postgres), 8000 (backend), 5173 (frontend) free on the host.
- `.env` present at the repo root (copy from `.env.example` if starting
  fresh; fill in any provider credentials you want to exercise — OAuth
  client id/secret for Gmail/Outlook, AI Gateway keys — leaving them
  blank is fine for everything below except the specific steps that call
  them out).
- Run every command from the repo root unless a step says otherwise.

---

## Part A — scripted verification (existing `verify_*.sh`)

These already exist in the repo and were written incrementally,
milestone by milestone, each assuming the previous one passed. Run them
**in this exact order** — several are one-shot fresh-DB scripts that
wipe data, so running them out of order will re-wipe state a later
script expects to still be there.

| # | Script | Covers | Data-destructive? |
|---|---|---|---|
| 1 | `./verify_0008.sh` | M5 Layer 2 — migration 0008, fresh DB | **Yes** — drops the Postgres volume |
| 2 | `./verify_layer3.sh` | M5 Layer 3 — Delivery Engine Core | No |
| 3 | `./verify_layer4.sh` | M5 Layer 4 — Schemas | No |
| 4 | `./verify_layer5.sh` | M5 Layer 5 — API routes, live HTTP (now uses a fixed verify-user login-or-register, updated this session for the new auth gate) | No |
| 5 | `./verify_layer6.sh` | M5 Layer 6 — Frontend build | No |
| 6 | `./verify_layer7.sh` | M5 Layer 7 — Full-stack integration | No |
| 7 | `./verify_m6_1.sh` | M6.1 — Conversation/EmailMessage schema | No |
| 8 | `./verify_m6_2.sh` | M6.2 — Mailbox Sync | No |
| 9 | `./verify_m6_3.sh` | M6.3 — Thread Builder | No |
| 10 | `./verify_m6_4.sh` | M6.4 — Reply Intelligence | No |
| 11 | `./verify_m7_1_part1.sh` | M7.1 Part 1 — Event Infra/Workflow Engine core | No |
| 12 | `./verify_m7_1_part2.sh` | M7.1 Part 2 — pilot workflow execution | No |
| 13 | `./verify_m7_2.sh` | M7.2 — AI Gateway/Prompt Builder/Agent Runtime | No |
| 14 | `./verify_m7_3.sh` | M7.3 — Supervisor/Orchestrator | No |
| 15 | `./verify_m7_4.sh` | M7.4 — Autonomous Multi-Agent Workflows | No |
| 16 | `./verify_m8_5.sh` | M8.5 — Event Backbone & Notification Center | No |
| 17 | `./verify_m8_6.sh` | M8.6 — Real-Time Event Streaming | No |

**Pass/fail criteria:** every script uses `set -euo pipefail` and
`assert`-style checks — a script that runs to completion and prints its
final success line passed; any non-zero exit or `FAILED:`/`AssertionError`
output is a fail. Stop and report which script failed and its full
output rather than continuing past it.

**Known change relevant here:** `verify_layer5.sh`'s live-HTTP check was
edited this session because `POST /auth/register` is no longer open —
it now logs in with a fixed verify-user email first and only registers
if that fails (which only succeeds on a truly fresh DB, i.e. right after
`verify_0008.sh`'s wipe). If you run `verify_layer5.sh` again later
against a DB that already has users, it should still pass via the login
path — if it instead fails with a 403 on register, that would indicate
either the bootstrap exception behaved unexpectedly or the script's fixed
verify-user account doesn't exist yet in this environment; either is
worth reporting, not silently working around.

---

## Part B — manual verification (no script exists yet)

Nothing in Part A covers anything from M8.7 onward — the design system
migration, Command Center, Workflow Engine domain wiring, Analytics/
Reports, Conversations UI, CRM Automation, World Map, Global Delete
System, or this session's own fixes. This is the exact "verification
coverage gap" Track A flagged as Priority 3, deferred until after the
architectural fixes landed — those fixes are done now, so writing actual
`verify_m8_7.sh`-style scripts for this range is a reasonable next step,
but is not part of this document; what follows is a manual checklist to
use in the meantime.

Bring the stack up first if it isn't already:
```
docker compose up -d
```
Then open `http://localhost:5173` and log in (use the fixed verify-user
from Part A, step 4, or your own admin account).

**Command Center / dashboard**
- [ ] Command Center loads without console errors; KPI strip, World Map,
      AI Workforce, and Attention Deck zones all render.
- [ ] World Map (M8.16): country paths are clickable; hovering a country
      shows a tooltip with country name + prospect count; countries with
      no prospect data show an honest "no data" state rather than a
      fabricated value.

**AI Workforce / Workflow Engine wiring (M8.13–M8.15)**
- [ ] Start a Discovery search, Research request, Personalization
      request, and Outreach request each from the UI; confirm each
      shows a live Workflow Execution View that reaches a terminal state
      (completed/failed), not a stuck "running" spinner.

**Analytics / Reports (M8.9)**
- [ ] Analytics page renders real aggregated data (not placeholder text)
      once at least one of the above requests has completed.
- [ ] Reports page's list→detail flow opens a real run's detail view.

**Conversations / CRM Automation (M6.5/M6.6)**
- [ ] Conversations page lists at least one conversation (requires a
      configured mailbox connection to populate real data — skip with a
      note if none is configured in this environment).
- [ ] Recommended Actions panel appears on a conversation and reflects
      a real Task row, not a placeholder.

**Global Delete System (M8.17) — excluding ProspectContact, reserved for
B2**
- [ ] Delete a Company Product, Knowledge Base entry, and a Sending
      Profile from their respective pages: confirmation dialog appears,
      success toast on delete, list refreshes without a manual reload.
- [ ] Delete a non-current Outreach Playbook version; confirm a playbook
      version still referenced by an Outreach Draft/Request correctly
      fails with a clear error (RESTRICT in effect), not a 500.
- [ ] Confirm `DiscoverySearches.tsx` still has **no** Delete button
      (deliberate — see deferred-items item 1) and that calling
      `DELETE /company-profiles/{id}/discovery-searches/{search_id}`
      directly against a search with real Job/Run history now returns a
      clean 400, not a 500 or a silent cascade (this exercises this
      session's migration 0023 fix directly; full re-verification of
      this specific fix is still B2's job, but a quick direct check here
      is low-risk and catches a gross regression early).

**Legacy Company/Contact Phase 1 deprecation (this session)**
- [ ] Sidebar shows a "Legacy" badge on both **Pipeline** and
      **Contacts** (previously only Pipeline had it).
- [ ] Contacts page shows the same amber `TransitionalBanner` Pipeline
      already had.
- [ ] `/api/v1/docs` (Swagger UI) shows `/companies` and `/contacts`
      routes marked deprecated (strikethrough or a "Deprecated" tag,
      depending on Swagger UI version) — confirms `deprecated=True` took
      effect and didn't break route registration.

**Notifications / Realtime (M8.5/M8.6)**
- [ ] Trigger an event (e.g. complete a Discovery run) and confirm a
      notification appears in the Notification Center without a manual
      page refresh (Realtime streaming working).

---

## Explicitly out of scope for B1 (reserved for B2)

Do not use this document to conclude these are verified — they require
their own dedicated re-verification pass:

- ProspectContact delete/archive behavior (the RESTRICT fix, the new
  archive/unarchive routes, and the default-hide-archived list filter).
- Multi-business isolation (the legacy Company/Contact tenant-scoping
  question Track A originally flagged).
- The authentication registration flow (the new admin gate and its
  bootstrap exception — confirm the bootstrap path fires only once on a
  truly fresh DB, and that a second registration attempt without an
  admin token correctly 403s).

---

## Reporting back

For each Part A script: pass/fail, and full output if fail. For each
Part B checklist item: pass/fail/skipped-with-reason. Once this comes
back clean, B2's three items are the last verification step before this
platform's first Comprehensive Verification pass can be closed out.
