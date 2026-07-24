# M2 Phase 2 UX Review — Provider Visibility & the Search Depth/Frequency Question

**Status: DRAFT — review only, no code written against this document yet.**
Requested by the CEO after Phase 2 backend verification passed (46/46
smoke tests): the Search Service/Provider Registry/Query Planner/Brave
Search architecture is real, but nothing about it is visible to an end
user. This document reviews the current frontend against what the
backend now actually offers, names the trade-offs for each open
question, and gives a concrete recommendation. Builds on
`docs/architecture/m2-discovery-provider-strategy.md` (the approved
Phase 2 architecture) and the Phase 2 implementation itself
(`app/discovery/providers/registry.py`, `search_service.py`,
`query_planner.py`).

---

## 1. What's actually true today (verified against the code, not assumed)

- **Providers**: `frontend/src/pages/DiscoverySearches.tsx` hardcodes
  `AVAILABLE_PROVIDERS = [{ key: "manual_csv", label: "Manual / CSV
  Import" }]`. `brave_search` was added to the backend registry in
  Phase 2 and is invisible in the UI — a user has no way to select it,
  see that it exists, or tell whether it's configured. There is also no
  backend API route that exposes the registry at all
  (`registry.iter_enabled_providers()`/`get_provider(key).health()`/
  `.capabilities()` exist but nothing in `app/api/routes/` calls them) —
  the frontend has no way to discover providers dynamically even in
  principle right now.
- **Provider health**: no concept of it anywhere in the UI. A business
  could enable `brave_search` on a search with no `BRAVE_SEARCH_API_KEY`
  configured and would only find out when the job comes back
  `partially_completed` with a buried error message.
- **Which provider found a prospect**: `ProspectRead.sources` (a list of
  `ProspectSourceRead`, each carrying `provider_key`) is already
  returned by `GET .../prospects` today. The frontend's `Prospect`
  interface in `Prospects.tsx` doesn't even declare the field, so it's
  silently dropped.
- **Which providers ran on a job**: `DiscoveryJobRead.providers_used`
  and the full `provider_runs` (per-provider status/duration/cost) are
  already returned by `GET .../discovery-jobs` and already rendered as
  plain text in `DiscoveryJobs.tsx` — the data exists, it's just text,
  not a scannable badge row.
- **Search Depth** (`quick`/`standard`/`deep`): grepped the entire
  `app/discovery/` tree. It is read in exactly one place —
  `pipeline.py` copies it into `DiscoveryRun.config_snapshot` for
  audit purposes. It does not change `MAX_VARIATIONS_PER_PLAN` (a flat
  50, unconditional), the number of Brave results requested (`count: 20`,
  hardcoded in `brave_search.py`), or anything about `manual_csv`. **It
  is not abstract-feeling by accident — it currently does nothing.**
  Same category of problem as Search Frequency, just not labeled
  honestly as such in the UI.
- **Search Frequency** (`manual`/`daily`/`weekly`): `ICPCriteria.
  search_frequency`'s own model docstring already says the quiet part
  out loud — *"Stored now, not yet acted on - scheduling automation is
  a later milestone."* The UI's "(not yet automated)" suffix on the two
  non-manual options is the one place in this feature that IS being
  honest about a gap — but it still lets a user select a setting that
  has zero effect, silently.

The common thread: this feature has **two fields that promise behavior
the system doesn't implement (Search Depth, Search Frequency)** and
**four pieces of real, already-computed provider data that exist in API
responses but never reach the screen**. These are different problems
with different fixes — worth separating cleanly rather than solving
with one UI pass.

---

## 2. Search Frequency: should Daily/Weekly stay visible?

Four options, as posed:

**Option 1 — leave as-is (visible, "(not yet automated)" suffix).**
Cheapest (zero work). Downside: it's a passive-honesty pattern, not an
active one — a user has to read a parenthetical to learn the setting
does nothing, and nothing stops them from picking it, closing the tab,
and assuming a daily search is now running. That's a real trust risk
for a product whose whole pitch is "this works while you're not looking
at it."

**Option 2 — disable with an explanation (grayed out, tooltip/label:
"Coming soon — runs stay manual until scheduling ships").**
Small, bounded frontend work (a `disabled` attribute + a `Tooltip`,
both already in the design system). Keeps the roadmap signal — a
prospective automation user SEES that recurring search is coming,
which matters for a product positioning itself as an AI Sales
Operating System, not just a one-shot search tool. Actively prevents
the false-confidence failure mode in Option 1.

**Option 3 — remove entirely until the scheduling milestone ships.**
Also cheap. Maximally honest (nothing to misread). Downside: it hides
the roadmap direction from a user who might specifically want to know
this is coming, and it's marginally MORE churn later (re-adding the
option, however trivial, is still a diff two milestones from now vs.
one flag flip today).

**Option 4 — implement the automation now.**
This is not a UI decision, it's a new milestone. Real automation needs:
a scheduler (a new periodic worker, mirroring the existing
`WORKFLOW_STEP_RUNNER_POLL_INTERVAL_SECONDS`-style pattern), per-search
"when did this last run" state, idempotent skip-if-already-run-today
logic, a real answer to "what happens to `brave_search`'s API cost when
a search silently re-runs itself daily with no one watching the bill,"
and its own approval gate. Bundling it into a UX cleanup pass would be
exactly the kind of undersized, unapproved scope creep this project's
discipline exists to prevent.

**Recommendation: Option 2.** Disable, don't hide, and don't build.
Pair it with a one-line addition to this same UI treatment for **Search
Depth** — since it's equally non-functional today, it deserves the same
honesty rather than looking "finished" while Search Frequency looks
"in progress." Concretely: keep all three Search Depth values selectable
(unlike Frequency, choosing "deep" vs "quick" isn't misleading in a
harmful way — it just does the same thing as "quick" right now), but
add a small inline note ("not yet used to vary search scope") so it
doesn't imply tuning that isn't happening. Frequency gets the stronger
treatment (disabled) because selecting "Daily" implies an ongoing
commitment the system silently fails to honor — a materially different
failure mode than Search Depth's "this dropdown is a no-op today."

If the CEO prefers stricter minimalism, Option 3 is a fully acceptable
alternative — the real cost difference between 2 and 3 is small. I'd
only push back on Option 1 (status quo) and Option 4 (out of scope
here).

---

## 3. Making the provider architecture visible — without building a big UI

Ranked by cost-to-value, cheapest first. None of these require a new
page.

### 3a. Prospect → provider badge (frontend-only, no backend change)
`ProspectSourceRead.provider_key` is already in every `GET .../prospects`
response. Add `sources: ProspectSourceRead[]` to the frontend `Prospect`
type and render one small `Badge` per distinct `provider_key` next to
the existing status badge in `Prospects.tsx`. This is the single
highest-value, lowest-cost item on this list — it also gives real,
visible payoff to Phase 2's own cross-provider dedup audit trail (a
prospect re-sighted by both `manual_csv` and `brave_search` now visibly
carries both badges, which is the concrete, user-facing proof that
dedup worked, not just a passing test).

### 3b. Discovery Job → provider badges (frontend-only, no backend change)
`DiscoveryJobRead.providers_used`/`provider_runs` are already fetched.
Add a row of small status-colored `Badge`s (one per provider, colored by
that provider's run status — completed/failed/cancelled) above the
existing detailed per-provider text lines in `DiscoveryJobs.tsx`. Keep
the detailed lines for anyone who wants duration/cost/request-count;
the badges are for at-a-glance scanning of "did brave_search actually
run."

### 3c. A real Provider Registry read endpoint (small backend addition)
One new route, e.g. `GET /discovery/providers`, that calls
`registry.iter_enabled_providers()` plus, for every registered key,
`get_provider(key).provider_name()`/`.health()`/`.capabilities()`.
Returns `[{key, name, enabled, capabilities}]`. This is genuinely small
— the logic already exists in `registry.py`; this is a thin read-only
wrapper, no new table, no migration. It replaces `DiscoverySearches.tsx`'s
hardcoded `AVAILABLE_PROVIDERS` array with a real fetch, which is what
makes `brave_search` (and anything registered after it) show up without
a frontend deploy every time a provider is added.

### 3d. Provider health indicator (frontend, depends on 3c)
Once 3c exists, render a small dot/`Badge` next to each provider
checkbox — green if `health()` is true, gray/amber if false, with a
tooltip explaining why (e.g. "BRAVE_SEARCH_API_KEY not configured").
Directly answers "why did my job come back partially_completed" before
a user ever has to run one to find out.

### 3e. "Coming Soon" providers (frontend-only, static list)
For `OpenCorporates` (Phase 3) and anything else on the named roadmap:
a small, static frontend array (NOT a backend concept — these providers
don't exist as code yet, so there's nothing for a registry endpoint to
report) rendered as visually disabled entries with a "Coming soon"
`Badge`, alongside the real, registry-backed providers from 3c. This is
deliberately kept as dumb, static frontend data — inventing a backend
"planned provider" concept for this would be over-building for what's
just a roadmap teaser.

### Suggested order
3a and 3b first — pure frontend, zero backend risk, immediate payoff,
and they're the two items closing the biggest gap (Phase 2's own
cross-provider work is currently invisible even though it's real and
tested). Then 3c, which is small and unlocks 3d. 3e can land whenever —
it's cosmetic and has no dependencies.

None of this requires a new page, a new table, or a new migration. The
entire visible surface is: two small `Badge` additions to two existing
pages, one new thin GET route, and one static array.

---

## 4. What I'm NOT proposing here

- No scheduling/automation implementation (Option 4 above) — a real
  future milestone, not a UX fix.
- No new "provider marketplace" page, no per-provider settings/config
  UI beyond the existing enabled-in-`.env` model — `capabilities()`/
  `health()` are read-only signals for this phase, not configuration
  surfaces.
- No change to Search Depth's actual behavior (making it real, e.g.
  scaling `MAX_VARIATIONS_PER_PLAN` or Brave's result count by depth) —
  that's a legitimate future enhancement to the Query Planner, not a UX
  task, and is out of scope for this review.

---

## Summary / decision needed

1. Search Frequency: recommend **disable Daily/Weekly with an
   explanation** (Option 2), and apply the same "not yet wired" honesty
   treatment to Search Depth (lighter touch — inline note, not
   disabled).
2. Provider visibility: recommend building, in order, **3a → 3b → 3c →
   3d → 3e** — two frontend-only badge additions first (zero backend
   risk, immediate payoff), then one small registry endpoint, then the
   health indicator it unlocks, then the static "coming soon" list.

Awaiting approval before writing any code.
