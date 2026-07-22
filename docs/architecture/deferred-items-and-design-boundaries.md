# Deferred items and permanent design boundaries — M8.16/M8.17 post-implementation review

**Status:** written at the close of M8.16 (World Map Geometry
Verification) and M8.17 (Global Delete System), after both were
implemented and approved. Like `m5-production-readiness.md`, this is not
a proposal — nothing below is a design change up for debate. It documents
decisions already made (five items either deliberately left unbuilt, or
built narrower than originally scoped) so a future contributor — human or
AI — finds a clear record instead of rediscovering the same conflict from
scratch, or worse, "fixing" what looks like a missing feature and
quietly breaking an explicit guarantee this project depends on.

Two of the five items below were discovered *during* M8.17 implementation
itself, surfaced to the CEO rather than shipped silently, and approved as
exclusions. The other three were flagged during the M8.17 architectural
review before implementation began. All five share the same shape: a
piece of functionality that looks like an oversight from the outside, but
is actually a deliberate boundary protecting a stronger guarantee
elsewhere in the architecture.

---

## 1. Discovery Search deletion

**Current state:** `DELETE /company-profiles/{id}/discovery-searches/{search_id}`
exists and works (`app/api/routes/discovery_searches.py`), and has since
before M8.17. No frontend page has ever called it — `DiscoverySearches.tsx`
has no Delete button, and M8.17 deliberately did not add one.

**Reason it was deferred:** M8.17 was explicitly scoped to keep
"Workflow Engine history, Research runs, Outreach executions,
Personalization executions, and other audit records immutable." Discovery
Search deletion turned out to violate that guarantee, so it was pulled
back out mid-implementation rather than shipped.

**Why execution history must remain immutable:** every AI domain in this
platform (Discovery, Research, Personalization, Outreach) is built on the
principle that a Job/Run record is a permanent, explainable account of
what the AI actually did and when — the same principle behind this
project's "no fabricated data" and "explainable, auditable" standing
requirements, and the reason `WorkflowExecutionView` and the Event
Backbone exist at all. If a Job/Run record can be silently destroyed by
deleting an unrelated configuration object, the platform can no longer
guarantee that history is complete — a support conversation, a
compliance question, or a future AI agent reasoning over "what has this
business tried before" would all be working from a record that might
have gaps nobody can detect after the fact, because there'd be no trace
that anything was ever removed.

**The FK/cascade issue, exactly:**

- `DiscoveryJob.discovery_search_id` → `discovery_searches.id`,
  `ondelete="CASCADE"` (`app/models/discovery_job.py`)
- `DiscoveryRun.discovery_search_id` → `discovery_searches.id`,
  `ondelete="CASCADE"` (`app/models/discovery_run.py`)

`DiscoveryRun`'s own docstring calls it a "frozen, permanent record of
one execution of a DiscoverySearch." Deleting the parent `DiscoverySearch`
row today would cascade-delete every `DiscoveryJob` and `DiscoveryRun`
row referencing it at the database level — silently, successfully, and
irreversibly. There is no application-level guard in front of this; the
existing `delete_discovery_search` route simply calls `db.delete(search)`
and commits.

**Current limitation:** the only thing preventing this from being a live
data-loss bug today is that no frontend page exposes the delete button.
The backend route is fully capable of destroying real execution history
right now, for anyone who calls it directly (e.g. via the API docs or a
script). This should be treated as an open risk, not a closed one.

**Recommended future milestone:** a small, standalone "Discovery Search
deletion safety" fix — not bundled with a new feature milestone, since
it's a correctness fix to existing schema, not new functionality.

**Recommended implementation approach:** change both foreign keys from
`ondelete="CASCADE"` to `ondelete="RESTRICT"`, matching the pattern
already used successfully elsewhere in this exact scope (`search_templates`
→ `discovery_search.search_template_id` is `RESTRICT`;
`outreach_playbooks` → `outreach_draft`/`outreach_request` are `RESTRICT`).
Concretely:

1. A new Alembic migration altering both FK constraints to `RESTRICT`.
2. `delete_discovery_search` gains the same `try/except IntegrityError`
   pattern `delete_outreach_playbook` already uses, returning a clear
   400 ("this search has Discovery Job/Run history and can't be
   deleted") instead of a raw 500 on constraint violation.
3. Only then does the frontend Delete button described in M8.17's
   research become safe to add — the DB, not client-side logic, is what
   should make the guarantee airtight, the same way it already does for
   Outreach Playbooks.

An alternative, softer option considered and not recommended: `SET NULL`
instead of `RESTRICT` (matching `Prospect.discovery_search_id`'s own
pattern). Rejected because it would let the delete silently succeed while
orphaning real Job/Run history from its configuration context — worse
for explainability than an outright block, even though it wouldn't
destroy rows. `RESTRICT` is the correct choice specifically because these
are audit records, not just related data.

---

## 2. ICP Criteria deletion

**Current state:** `DELETE /company-profiles/{id}/icp-criteria/{icp_id}`
exists and works (`app/api/routes/icp_criteria.py`). `CompanyICP.tsx` has
no Delete button and never has; M8.17 did not add one.

**Reason it was deferred:** `CompanyICP.tsx`'s own on-page copy tells the
user: *"Every save creates a new version — nothing is lost, and you can
always look back at how your criteria evolved."* Adding a Delete button
to any row in that same page's "Version history" list would directly
contradict a guarantee the product itself makes, in its own words, to the
person using it.

**Why deleting would contradict the product's historical evolution
model:** ICP Criteria is deliberately versioned rather than edited in
place — the same "clone forward, never overwrite" pattern this codebase
also uses for Outreach Playbooks (`revise` → new version) and Personalization
snapshots. The entire point of that pattern is that a business's ICP can
be inspected retrospectively: which version was active when a given
Discovery Search ran, how targeting criteria narrowed or broadened over
time, why a particular prospect was or wasn't matched. Allowing an old
version to be deleted breaks that retrospective story for exactly the
version removed, even if it doesn't cascade into any other table's rows
being destroyed.

**Current limitation:** unlike Discovery Search, this is not a
CASCADE/data-loss risk — `DiscoverySearch.icp_criteria_id` is
`ondelete="SET NULL"`, so deleting an in-use ICP version wouldn't destroy
anything else, it would just silently null out which ICP snapshot a saved
search was configured against. The limitation here is entirely about the
product's own stated promise, not database safety.

**Recommended future milestone:** none needed as a fix — this is
correctly a permanent "no delete" boundary, not a temporary gap. If a
cleanup need emerges later (e.g. a business accumulates dozens of
abandoned draft versions), the right future addition would be an
"archive" concept parallel to Prospect's (`is_archived`-style flag that
hides a version from the default view without removing it) rather than
literal deletion — see item 4 below for why archive-over-delete is this
project's standing preference wherever a historical record has value.

**Recommended implementation approach:** none required now. If archival
is ever built, it should hide old, non-current ICP versions from the
default "Version history" view while keeping the row (and its "nothing is
lost" guarantee) fully intact — additive, not a replacement for the
existing versioning behavior.

---

## 3. Templates without management UI (Research templates, Personalization templates, Search templates)

**Current state:** all three have real, working backend CRUD including
`DELETE` routes (`research_templates.py`, `personalization_templates.py`,
`search_templates.py`, all using the same `get_owned_company_profile`
ownership guard as everything else). None has a frontend page that lists,
edits, or deletes them as first-class rows. Each is only ever fetched to
populate a `<select>` dropdown — `ProspectResearch.tsx` and
`ProspectStrategy.tsx` show templates only when starting a new
Research/Personalization request; `DiscoverySearches.tsx` shows Search
Templates the same way.

**Reason it was deferred:** M8.17 was scoped as "implement a consistent
delete experience" for entities that already have a management UI to
attach a Delete button to. These three don't have one — there is no
existing page showing "here are all your Research Templates, each with
Edit/Delete" the way `CompanyProducts.tsx` or `OutreachPlaybooks.tsx` do.

**Why delete requires dedicated management pages rather than simply
wiring buttons:** a Delete button needs somewhere to live — a list of
rows, each with an identity a user can recognize and choose to remove.
Bolting a Delete action onto a `<select>` dropdown built for "pick one to
start a request" would conflate two different jobs (choosing a template
to use vs. managing the set of templates that exist) inside one small
control, and would very likely ship without whatever ownership/usage
context a real management page would show (e.g. "used by 4 active
Research Requests already"). This is new page-building work, not a
wiring task — exactly the kind of scope creep this milestone's own
"do not add new features" boundary (mirrored from M8.16) was meant to
prevent.

**Current limitation:** these three template types can only be created
via direct API calls today (no create form either) beyond whatever
system-default rows a migration seeded — there is no in-product way to
manage the full lifecycle of a template, delete being only one missing
piece of a larger gap.

**Recommended future milestone:** a "Template Library" milestone (one
candidate number: M8.18, or folded into whichever future milestone
covers Research/Personalization/Discovery configuration management more
broadly) — scoped explicitly to build list/create/edit/delete pages for
all three template types in one consistent pattern, likely reusing
`OutreachPlaybooks.tsx`'s existing versioned-list-with-actions layout as
the template (no pun intended) rather than inventing a fourth pattern.

**Recommended implementation approach:** one page per template type (or
a single tabbed page, given how structurally similar the three are),
each showing existing rows with Edit and Delete, built on the same
`ConfirmDialog`/`useDeleteResource` primitives M8.17 already established
— at that point, wiring delete is the easy, last step, not the starting
point. Before deleting, check for the same RESTRICT-style protection
Discovery Search deletion is missing today: confirm
`research_templates`/`personalization_templates`/`search_templates` are
each protected by `RESTRICT` from their respective Request tables
(already true — see item 1's FK inventory) so this new UI is safe by
construction from day one, unlike Discovery Search's retrofit.

---

## 4. Company / Prospect / Contact lifecycle — prefer archive over hard delete

**Current state:** `Prospect` already has a real, working, non-destructive
lifecycle: `approve` / `reject` / `archive` actions and an `ARCHIVED`
status value (`ProspectStatus` enum), with a working Archive button in
`Prospects.tsx`. `Company` (the pipeline lead/target-company record,
`app/models/company.py`) has no `PUT`, `DELETE`, or archive action at
all. `Contact` (the top-level address-book entity, distinct from
`ProspectContact`) has no delete or archive action either.
`ProspectContact` has a working hard-`DELETE` route, but zero frontend
CRUD UI of any kind exists for it today.

**Recommendation:** wherever a historical or relationship-tracking value
exists in one of these three entities, prefer building (or reusing) an
archive-style lifecycle over adding hard delete — this is a standing
architectural preference for this project going forward, not a one-off
decision scoped to M8.17.

**Reasoning:** `Prospect` already proves the pattern works well here: a
business's CRM history (which leads were pursued, rejected, or set aside)
has ongoing value the same way Discovery Job history does, just at the
individual-prospect level rather than the execution level. Hard-deleting
a `Company` or `Contact` a business has already engaged with (sent
outreach to, held conversations with, generated Research on) would
silently erase that relationship history with no equivalent "frozen
record" left behind, unlike execution history (item 5) which has its own
dedicated Job/Run tables specifically to survive exactly this kind of
cleanup. Contacts and Companies don't have that separate historical
record — the row *is* the history — so removing it removes the history
outright.

**Current limitation, per entity:**

- **Company** — no lifecycle action exists yet (no archive, no delete).
  Out of scope for M8.17 because adding one would be new backend
  functionality, not "wire delete into an existing action."
- **Contact** — same: no lifecycle action, and unlike Company, no
  frontend page manages Contacts at all yet (they only appear read-only,
  inside `Reports.tsx`/`Prospects.tsx`'s own displays).
- **ProspectContact** — has hard delete already, but with zero frontend
  UI to reach it; also has no archive alternative, meaning if a
  management UI is ever built for it, the same "prefer archive" question
  applies before wiring its existing delete route to a button.

**Recommended future milestone:** whichever future milestone builds
real Contact/Company management UI (likely alongside, or a prerequisite
to, the "Pipeline entities" work referenced loosely in earlier scoping
conversations) should include an explicit design decision — archive vs.
delete — made the same way `Prospect`'s was, before any delete button
ships for either entity.

**Recommended implementation approach:** for `Company`, add an
`is_archived`/`ARCHIVED`-stage-style lifecycle mirroring `Prospect`'s
exactly (this project already has `PipelineStage` on `Company` — a
natural fit would be treating archive as a terminal stage, consistent
with how `ProspectStatus.ARCHIVED` already works). For `Contact` and
`ProspectContact`, a simpler `is_active`/`archived_at` nullable-timestamp
column would suffice given they don't carry a multi-stage pipeline
concept the way `Company`/`Prospect` do. In both cases, hard delete
should remain available only as a narrow, RESTRICT-protected fallback
for genuinely mistaken/duplicate rows with no real history attached yet
— never the primary removal action surfaced in the UI.

---

## 5. Workflow execution history — permanent immutability

**Current state:** no delete route exists anywhere for `DiscoveryJob`,
`DiscoveryRun`, `ResearchJob`, `ResearchRun`, `PersonalizationJob`,
`PersonalizationRun`, `OutreachJob`, `OutreachRun`, `WorkflowInstance`,
`WorkflowDefinition` execution records, or any `Event` row. This is
correct and should stay this way.

**Explicit statement, for the record:** Workflow Engine executions
(every `WorkflowInstance` and the `Job`/`Run` pairs each domain pipeline
produces underneath it — Discovery, Research, Personalization, Outreach)
and the Event Backbone's own `Event` rows are **intentionally immutable
by design, permanently, not as a temporary gap awaiting a future
milestone.** No future milestone should add delete support for any of
these tables. This is the single load-bearing guarantee the entire
"AI-first, explainable, auditable, no fabricated data" architecture
promises the business: at any point, for any AI-driven action this
platform has ever taken, there is a complete, permanent, inspectable
record of what happened, when, and what it produced.

**Why this matters architecturally:** `WorkflowExecutionView` (the
shared frontend component every domain's Live Workflow Progress screen
reuses), the Event Backbone (`app/workflow_engine/events.py`, consumed by
Notifications, Realtime Streaming, and the Workflow Dispatcher — three
independent systems all trusting the same event log), and this project's
own recurring verification discipline (real, executed unit tests over
`py_compile`-only checks wherever possible; smoke tests confirming exact
event sequences) all assume this history is permanent. Any future
feature that appears to require deleting a Job/Run/Event row (bulk
cleanup, storage cost, "hide old noise from the UI") should be solved
with an archival/hide-from-default-view mechanism — the same
`is_archived`-style pattern recommended in item 4 — never with an actual
`DELETE`.

**Recommended future milestone:** none — this is not deferred work, it's
a permanent boundary. If storage/volume ever becomes a real operational
concern, the correct future milestone is "execution history archival"
(e.g. moving old rows to cold storage, or a `hidden_from_default_view`
flag), explicitly scoped to preserve every row's existence and content,
never scoped as "add a delete button."

**Recommended implementation approach:** n/a for deletion. If archival
is ever pursued, it should be additive (a new nullable column/flag) and
should never touch the existing Job/Run/Event tables' `DELETE`
permissions, which should remain absent.

---

## Summary table

| Item | Delete route exists? | Frontend UI exists? | Safe to wire delete today? | Status |
|---|---|---|---|---|
| Discovery Search | Yes | No (deliberately not added) | No — CASCADE destroys Job/Run history | Blocked pending FK migration (item 1) |
| ICP Criteria | Yes | No (deliberately not added) | Technically yes, but contradicts product's own "nothing is lost" promise | Permanently excluded by design |
| Research/Personalization/Search Templates | Yes | No (no management page at all) | N/A — nothing to wire yet | Needs new management UI first (item 3) |
| Company | No | No | N/A | Needs archive lifecycle built (item 4) |
| Contact | No | No | N/A | Needs archive lifecycle built (item 4) |
| ProspectContact | Yes | No | Undecided — archive-vs-delete question unresolved | Needs a decision before any UI (item 4) |
| Prospect | No (has archive instead) | Yes (Archive button, working) | Already solved correctly | No action needed |
| CompanyProfile | Yes | No | Highest blast-radius action in the system | Deliberately excluded, needs its own dedicated review (not covered above — see M8.17 chat summary) |
| Discovery/Research/Personalization/Outreach Job/Run, WorkflowInstance, Event | No | No | Never — permanent immutability | Working as designed (item 5) |
