# Deferred items and permanent design boundaries — M8.16/M8.17 post-implementation review

**Status:** originally written at the close of M8.16 (World Map Geometry
Verification) and M8.17 (Global Delete System). Updated after the
platform's first Comprehensive Verification pass (Track A) surfaced a
second, more severe instance of item 1's exact CASCADE problem
(ProspectContact → Outreach/Delivery execution history) plus two adjacent
architectural fixes (legacy Company/Contact staged deprecation, interim
admin gate on user registration) — all three approved and implemented
together. Like `m5-production-readiness.md`, this is not a proposal for
the items marked resolved below — those decisions are already made and
shipped. Unresolved items remain open design boundaries, documented so a
future contributor — human or AI — finds a clear record instead of
rediscovering the same conflict from scratch, or worse, "fixing" what
looks like a missing feature and quietly breaking an explicit guarantee
this project depends on.

Two of the original five items were discovered *during* M8.17
implementation itself, surfaced to the CEO rather than shipped silently,
and approved as exclusions. The other three were flagged during the
M8.17 architectural review before implementation began. The platform-wide
lifecycle rule and items 6-7 were added after the Track A verification
pass, following the same discipline: surfaced, analyzed, approved, then
implemented in small isolated commits.

---

## 1. Discovery Search deletion

**RESOLVED (migration 0023, `app/api/routes/discovery_searches.py`).**
Both FKs below were changed to `ondelete="RESTRICT"` and
`delete_discovery_search` now catches the resulting `IntegrityError` and
returns a 400, exactly as this section originally recommended. The
"current limitation" and "recommended implementation approach"
paragraphs below are left in place, unedited, as the historical record of
why this was necessary — the frontend Delete button described there
still does not exist and remains a future, deliberately-not-yet-built
step, not implied by this fix.

**Current state (as originally written, now superseded by the fix
above):** `DELETE /company-profiles/{id}/discovery-searches/{search_id}`
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

**ProspectContact: RESOLVED (migrations 0023 + 0024,
`app/api/routes/prospect_contacts.py`).** The Track A verification pass
found a more severe version of item 1's exact problem: `ProspectContact`
had five `CASCADE` foreign keys reaching into real execution history
(`delivery_queue_items`, `outreach_drafts`, `outreach_requests`,
`outreach_jobs`, `outreach_runs`) — an entire domain's audit trail, not
one domain's job/run pair. Fixed the same way: all five changed to
`RESTRICT` (migration 0023), `delete_prospect_contact` now catches
`IntegrityError` and returns 400. On top of that, `ProspectContact` now
has the real archive lifecycle this section originally only recommended:
`is_archived` / `archived_at` / `archived_by_user_id` (migration 0024),
`POST .../contacts/{id}/archive` and `.../unarchive` routes, and
`list_prospect_contacts` hides archived contacts by default
(`?include_archived=true` to opt back in). Hard delete remains available
as the narrow, `RESTRICT`-protected fallback this section recommended,
not the primary removal path. No frontend UI was added for this in the
same change — `Prospects.tsx` has no per-contact archive/delete
affordance yet; that remains a future, deliberately-not-yet-built step.

**Company and Contact (the top-level, non-Prospect-scoped CRM
entities): still open**, but see item 6 below — both are now staged for
deprecation and eventual retirement rather than lifecycle investment, so
building an archive action for either is very unlikely to be the right
next step (why extend a model scheduled to be removed). The rest of this
section's reasoning about Company/Contact is left as historical context.

**Current state (as originally written):** `Prospect` already has a real,
working, non-destructive lifecycle: `approve` / `reject` / `archive`
actions and an `ARCHIVED` status value (`ProspectStatus` enum), with a
working Archive button in `Prospects.tsx`. `Company` (the pipeline
lead/target-company record, `app/models/company.py`) has no `PUT`,
`DELETE`, or archive action at all. `Contact` (the top-level address-book
entity, distinct from `ProspectContact`) has no delete or archive action
either. `ProspectContact` had a working hard-`DELETE` route, but zero
frontend CRUD UI of any kind existed for it — see the resolution above
for what changed.

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

- **Company** — no lifecycle action exists yet (no archive, no delete),
  and per item 6 below is now staged for deprecation rather than further
  investment — an archive action here is unlikely to ever be built.
- **Contact** — same as Company, and also staged for deprecation per
  item 6.
- **ProspectContact** — RESOLVED, see above: real archive lifecycle
  (`is_archived`/`archived_at`/`archived_by_user_id`), archive/unarchive
  routes, hide-by-default list filtering, and hard delete now RESTRICT-
  protected as the narrow fallback. Frontend UI to reach any of this is
  still missing (`Prospects.tsx` shows contacts read-only within a
  Prospect's detail view) — that remains open.

**Recommended future milestone (Company/Contact only — ProspectContact is
resolved, see above):** superseded by item 6's staged deprecation
decision. Building lifecycle/management UI for the legacy `Company`/
`Contact` models is no longer the recommended path now that they're
scheduled for retirement; effort should go into `Prospect`/
`ProspectContact` (the canonical replacement) instead. If, before Phase 2
retirement, a real business need forces a lifecycle action onto these
legacy models anyway, the same archive-vs-delete decision this section
originally called for still applies before any delete button ships.

**Recommended implementation approach (historical, for Company/Contact
only):** for `Company`, add an `is_archived`/`ARCHIVED`-stage-style
lifecycle mirroring `Prospect`'s exactly (this project already has
`PipelineStage` on `Company` — a natural fit would be treating archive as
a terminal stage, consistent with how `ProspectStatus.ARCHIVED` already
works). For `Contact`, a simpler `is_active`/`archived_at`
nullable-timestamp column would suffice given it doesn't carry a
multi-stage pipeline concept the way `Company`/`Prospect` do. This is the
exact pattern `ProspectContact` actually received (see the resolution
above) — kept here as the template if Company/Contact ever need the same
treatment despite item 6's retirement plan. Hard delete should remain
available only as a narrow, RESTRICT-protected fallback for genuinely
mistaken/duplicate rows with no real history attached yet — never the
primary removal action surfaced in the UI.

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

## Platform-wide lifecycle rule: archive over hard delete for any entity touching execution history

This is now a standing architectural rule for this project, generalized
from items 1 and 4 above rather than scoped to any single entity:

**Rule:** any entity that participates in execution history — meaning
some other table's Job/Run/queue/audit row holds a foreign key pointing
at it — must never allow that history to be silently destroyed by
deleting the entity. Concretely, this means two things together, not
either alone:

1. **Database level:** the foreign key from the execution-history table
   back to the entity must be `ondelete="RESTRICT"` (never `CASCADE`,
   and never `SET NULL` if doing so would require loosening a
   `nullable=False` column and touching downstream ORM/business-logic/
   reporting assumptions — see migration 0023's docstring for the full
   reasoning on why `RESTRICT` was chosen over `SET NULL` for exactly
   this kind of column). This is the guarantee that actually holds even
   if every application-layer check below is bypassed (a direct API
   call, a script, a future bug).
2. **Application level:** the entity gets a real, non-destructive
   lifecycle — an `is_archived`/`archived_at`-style pair (or, where a
   multi-stage pipeline already exists, an `ARCHIVED` terminal status
   value, as `Prospect` already does) — so removing an entity from
   active use never requires deleting the row at all. List views hide
   archived entities by default. Hard delete remains available only as a
   narrow fallback, and only succeeds when the `RESTRICT` constraint
   confirms no execution history actually exists — the database, not
   client-side logic, is what makes the guarantee airtight.

**Applied so far:** `Prospect` (pre-existing, the original proof this
pattern works), `ProspectContact` (item 4, migrations 0023/0024),
Discovery Search's `DiscoveryJob`/`DiscoveryRun` FKs (item 1, migration
0023, RESTRICT only — no archive lifecycle needed since `DiscoverySearch`
itself isn't deleted via an archive-style UI today).

**Not yet applied, tracked separately:** `Company`/`Contact` (item 6 —
staged for retirement instead, see below), the three template types
(item 3 — no management UI to attach a lifecycle action to yet).

**Why this belongs at the platform level and not just in one entity's
docstring:** every future milestone that adds a new execution-history
table (a new AI domain's Job/Run pair, a new queue/dispatch table) should
apply this rule automatically, by construction, rather than rediscovering
the CASCADE risk the way both item 1 and item 4 independently did during
verification passes. A contributor adding a new FK from a Job/Run/queue
table back to any entity should default to `RESTRICT` and ask "does this
entity need an archive lifecycle" as a standard design question, not a
special case.

---

## 6. Legacy Company/Contact model retirement — staged deprecation (Phase 1 complete)

**Current state:** `Company`/`Contact` (the M0-era, tenant-unscoped CRM
models — `app/models/company.py`, `app/models/contact.py`, plus
`WebsiteFinding`/`FollowUp` hanging off `Company`) were confirmed during
the Track A verification pass to be strict subsets of the live, tenant-
scoped `Prospect`/`ProspectContact` models field-by-field, with no
scenario where extending the legacy models would be the right move over
extending their replacements.

**Decision:** retire these models, but in two phases rather than
immediately, to minimize migration risk:

- **Phase 1 (this change, complete):** mark the legacy routes and UI as
  deprecated; prevent new development against the legacy models; do not
  physically remove anything yet.
  - `app/models/company.py`/`contact.py` docstrings now say DEPRECATED -
    Phase 1 (still live, do not extend — use Prospect/ProspectContact).
  - `app/api/routes/companies.py`/`contacts.py` routes now set
    `deprecated=True` (visible in OpenAPI/Swagger), with zero behavior
    change to any existing route.
  - `WebsiteFinding`/`FollowUp` — already confirmed in the Track A dead-
    code audit to have no route/service/frontend reference at all —
    were given the stronger `Thread`/`Message`-style "SUPERSEDED - do not
    use" docstring instead, since they are dead code today, not merely
    discouraged.
  - Frontend: `Contacts.tsx` now has the same "Legacy" nav badge and
    `TransitionalBanner` that `Pipeline.tsx` (the `Company` list) already
    had since M8.3/M8.7 — a real gap, since both pages read off the same
    M0 model family but only Pipeline had been marked. No redirect was
    added (`Pipeline.tsx` lists all companies unscoped by CompanyProfile;
    `Prospect` data is scoped per CompanyProfile and requires an active
    company selection, so a structural redirect isn't a clean fit — the
    existing banner text pointing users toward the real experience is
    the same treatment Pipeline already uses for this exact reason).

- **Phase 2 (future, not started):** verify zero remaining dependencies
  on the legacy tables, prepare a migration plan, then remove the tables.
  Not scheduled as part of this work — this document exists precisely so
  a future contributor picking up Phase 2 has the full context instead
  of rediscovering it.

**Recommended future milestone:** a dedicated "Legacy CRM retirement"
milestone for Phase 2, scoped to: confirm nothing (script, worker,
report) still reads `companies`/`contacts`/`website_findings`/
`followups`; write the drop-table migration; remove the now-dead
`app/models/company.py`, `contact.py`, `website_finding.py`, `followup.py`,
their routes, and `Pipeline.tsx`/`Contacts.tsx`.

---

## 7. User registration — interim admin gate pending M9 Organization & AI Workforce Management

**Current state:** `POST /auth/register` (`app/api/routes/auth.py`) now
requires the caller to be an authenticated admin (`UserRole.ADMIN`),
checked manually in the route rather than via the existing
`get_current_active_admin` dependency, with one necessary exception: if
zero users exist yet on a given deployment, registration stays open and
that first account is automatically granted admin. Without this
exception, a fresh install would have no way to create its first admin
at all — there is no seed script or CLI for user creation today, and
`get_current_active_admin` existed unused in `app/api/deps.py` before
this change (confirmed zero routes referenced it).

**This is intentionally, explicitly temporary — not the platform's
permanent registration model.** To be unambiguous for any future
contributor (human or AI) reading this file:

- The bootstrap exception exists **only** to support first-time
  initialization of a fresh deployment, before M9 exists. It is not a
  general-purpose account-creation convenience and should not be reused,
  extended, or repurposed for any other case.
- It is **expected to be replaced entirely** by M9's organization-scoped
  invitation and membership system — not extended, wrapped, or built on
  top of. When M9 is scoped, the correct move is to delete this bootstrap
  logic and this endpoint's flat admin check, not to add invitation logic
  alongside them.
- It **must never be treated as, or allowed to drift into, the platform's
  long-term registration architecture.** If a future milestone finds
  itself extending this mechanism rather than replacing it, that is a
  sign the milestone should be M9 itself, not a workaround around it.

**Reason this is interim, not permanent:** this project has no
organization-scoped invitation/membership system yet. A single flat
admin-gate is a reasonable stopgap for the current single-organization
reality, but is explicitly not the intended long-term shape — a future
M9 Organization & AI Workforce Management milestone is expected to
replace this endpoint entirely with org-scoped invitations and membership
management (an admin inviting a specific person to a specific
organization with a specific role, not a flat "any admin can create any
account" model). No permanent invitation system was designed as part of
this change, per explicit instruction — the code and documentation are
left in a state that naturally evolves into M9, not one that anticipates
its exact shape.

**Current limitation — how the bootstrap exception actually decides,
verified by direct code inspection, not assumption:** the entire gate is
one line — `is_bootstrap = db.query(User.id).first() is None` — re-
evaluated fresh on every request. There is no persisted "setup complete"
flag, timestamp, or environment marker anywhere; the condition is purely
"does the `users` table have any rows right now." This means:

- It is reachable under exactly one condition: the `users` table is
  empty at the moment a request hits this route. In the common case
  that's true exactly once (first boot), because nothing in the product
  today deletes users (confirmed: no `DELETE` route for `User` exists
  anywhere, and no seed/truncate script touches the `users` table).
- Nothing *structurally* prevents it firing again later — the invariant
  holds only because nothing empties the table today, not because the
  check itself remembers that initialization already happened.
- It **can** become reachable again after a migration downgrade to 0001
  (whose `downgrade()` drops the `users` table) followed by a re-upgrade,
  or after restoring a database backup taken before the first user
  existed, or pointing a fresh/misconfigured environment at an empty DB.
  None of these are hypothetical edge cases invented for caution — they
  are direct, verified consequences of the check being state-based
  ("is this table empty") rather than event-based ("has this ever
  happened before").
- There is also a narrow race condition: two concurrent unauthenticated
  `/auth/register` calls arriving before either commits would both read
  `is_bootstrap = True` under default transaction isolation, and both
  could be granted admin.

This was surfaced to, and explicitly reviewed and accepted by, the CEO as
a known, bounded characteristic of the interim mechanism — not an
oversight. It is considered acceptable for the current internal-tool,
single-tenant deployment model (a fresh install is expected to be
immediately configured by the deploying admin, not left publicly
reachable in an unconfigured state), but should be revisited before this
project's deployment model ever changes to self-service or public-facing,
and definitely before/during M9.

**Future security hardening (recorded here as future work, explicitly
NOT implemented and NOT a blocker for this milestone):**

1. Replace table-emptiness bootstrap detection with a more robust
   initialization mechanism — e.g. a one-way marker that survives a
   `users` table becoming empty again (a separate, never-dropped
   "system initialized" record, or an out-of-band signal such as an
   environment variable / file checked at deploy time) rather than
   re-querying table emptiness on every request.
2. Eliminate the bootstrap race condition described above (e.g. a
   serializable transaction or a unique constraint plus retry around the
   check-then-insert).
3. Ensure migration rollback/restore scenarios cannot silently reopen
   bootstrap registration — today, nothing distinguishes "genuinely fresh
   install" from "table is empty for some other reason."
4. Optionally emit an audit log entry whenever the bootstrap path is
   actually taken, so any unexpected re-trigger (post-rollback, post-
   restore, or otherwise) is visible to an operator immediately instead
   of silent.

None of these four are required for this milestone to be considered
complete — they are hardening for whenever this interim mechanism is
revisited, most likely as part of scoping M9.

**Recommended future milestone:** M9 Organization & AI Workforce
Management, as already anticipated by `assigned_user_id` on `Task`
(migration 0022) and `User.role` itself. When M9 is scoped, this
endpoint's bootstrap exception and flat admin check should be replaced
by org-scoped invitation tokens, not extended in place.

---

## Summary table

| Item | Delete route exists? | Frontend UI exists? | Safe to wire delete today? | Status |
|---|---|---|---|---|
| Discovery Search | Yes, now RESTRICT-protected + 400 on conflict | No (deliberately not added) | Yes at the DB level; UI still deliberately not built | **RESOLVED** (item 1, migration 0023) |
| ICP Criteria | Yes | No (deliberately not added) | Technically yes, but contradicts product's own "nothing is lost" promise | Permanently excluded by design |
| Research/Personalization/Search Templates | Yes | No (no management page at all) | N/A — nothing to wire yet | Needs new management UI first (item 3) |
| Company | No | No | N/A | Staged for deprecation, not lifecycle investment (item 6, Phase 1 complete) |
| Contact | No | No | N/A | Staged for deprecation, not lifecycle investment (item 6, Phase 1 complete) |
| ProspectContact | Yes, now RESTRICT-protected + 400 on conflict, plus real archive/unarchive | No (frontend UI still not built) | Yes — archive preferred, hard delete safe as narrow fallback | **RESOLVED** (item 4, migrations 0023/0024) |
| Prospect | No (has archive instead) | Yes (Archive button, working) | Already solved correctly | No action needed |
| CompanyProfile | Yes | No | Highest blast-radius action in the system | Deliberately excluded, needs its own dedicated review (not covered above — see M8.17 chat summary) |
| Discovery/Research/Personalization/Outreach Job/Run, WorkflowInstance, Event | No | No | Never — permanent immutability | Working as designed (item 5) |
| `POST /auth/register` | N/A (not a delete) | N/A | N/A | Admin-gated with bootstrap exception, interim pending M9 (item 7) |
