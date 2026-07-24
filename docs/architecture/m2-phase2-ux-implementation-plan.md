# M2 Phase 2 UX Implementation Plan — Provider Visibility + Honest Controls

**Status: DRAFT — plan only, no code written against this document yet.**
Follows CEO approval of `m2-phase2-ux-provider-visibility-review.md`'s
recommendations, with the CEO's own re-prioritization (Priority 1-4
below). Every file path and field name below was verified by reading
the actual current code, not assumed.

---

## Scope discipline

Everything in this plan is either (a) a pure frontend change against
data the API already returns, or (b) one small, new, read-only backend
endpoint plus two one-line additive methods on existing providers. **No
migration, no schema change, no change to `run_discovery_search()` or
any provider's `search()` behavior, no scheduling.** The one piece of
backend logic (`registry.py`) that changes at all gains a single public
accessor function - nothing about how providers are looked up, resolved,
or executed changes.

---

## Priority 1 — UI Honesty: Search Frequency

**File:** `frontend/src/pages/DiscoverySearches.tsx`, lines 306-311 (the
Search Frequency `<Select>`).

**Change:** add `disabled` to the `daily`/`weekly` `<option>` elements,
and put the explanation directly in the option's own visible text
(no tooltip needed - a disabled native `<option>` already reads clearly
as "not selectable," and native `<select>` doesn't support rendering a
separate tooltip per option anyway):

```tsx
<option value="manual">Manual</option>
<option value="daily" disabled>Daily — Available in a future automation milestone</option>
<option value="weekly" disabled>Weekly — Available in a future automation milestone</option>
```

**Why this satisfies "keep visible, clearly indicate unavailable, add
explanation" with zero new components:** a disabled `<option>` renders
grayed-out and is not selectable by mouse or keyboard in every browser,
which is the browser-native version of exactly what a custom "locked"
badge would otherwise have to fake. `form.search_frequency` already
defaults to `"manual"` (see `EMPTY_FORM`), so no existing saved search
can end up in an invalid state from this change alone.

**Integration note:** an EXISTING search that was saved with
`search_frequency: "daily"` before this change (unlikely in practice,
since the automation never ran, but not impossible if a business set it
anticipating the feature) will still display correctly - disabling the
option only blocks NEW selection, it doesn't hide or corrupt the
currently-selected value if the backend still returns `"daily"` for
that row. No data migration needed.

**Risk:** none identified. This is presentational only; the backend
schema/enum is untouched, and `search_frequency` already flows through
the API exactly as today.

---

## Priority 2 — Provider Architecture Visibility

### 2a. New backend endpoint: `GET /discovery-providers`

**New file:** `backend/app/api/routes/discovery_providers.py`, modeled
directly on `backend/app/api/routes/reference_data.py` (read-only,
`get_current_user`-only auth, NOT nested under
`/company-profiles/{id}/...` since provider availability is a
platform-wide fact, not tenant-specific data - identical reasoning to
why `/buyer-types`/`/industries`/`/countries` aren't nested either).

```python
router = APIRouter()

@router.get("/discovery-providers", response_model=list[DiscoveryProviderRead])
def list_discovery_providers(current_user: User = Depends(get_current_user)) -> list[DiscoveryProviderRead]:
    results = []
    for key in list_registered_provider_keys():  # new registry.py accessor, see below
        try:
            provider = get_provider(key)
            results.append(DiscoveryProviderRead(
                key=key, name=provider.provider_name(),
                enabled=provider.health(), capabilities=provider.capabilities(),
            ))
        except Exception:
            # A provider whose own class fails to import/construct
            # (e.g. a genuinely broken plugin, or - in a non-Docker
            # dev environment - a missing third-party dependency like
            # httpx) is reported as present-but-unhealthy, never a 500.
            # Mirrors registry.py's own iter_enabled_providers()'s
            # existing "never raises" contract.
            results.append(DiscoveryProviderRead(key=key, name=key, enabled=False, capabilities={}))
    return results
```

**New schema:** `backend/app/schemas/discovery_provider.py` —
`DiscoveryProviderRead(key: str, name: str, enabled: bool, capabilities: dict[str, Any])`.
Deliberately not tied to any ORM model (this isn't a table) - same
"plain Pydantic model over a computed value" shape
`WorkflowExecutionView`'s own backend read models already use elsewhere
in this codebase for non-table data.

**One small addition to `backend/app/discovery/providers/registry.py`:**
a public `list_registered_provider_keys() -> list[str]` returning
`list(_PROVIDER_IMPORT_PATHS)`. `_PROVIDER_IMPORT_PATHS` stays private
(leading underscore, internal wiring detail); this is the one
intentional, documented way for a caller outside `app/discovery/` to
learn what's registered, mirroring `iter_enabled_providers()`'s own
existing public-accessor pattern right next to it. **This is the only
production code touched in this entire plan beyond the two provider
methods below** — everything else is either a brand-new, additive file
or a frontend-only change.

**Registered in `backend/app/main.py`:** one new
`app.include_router(discovery_providers.router, prefix=API_PREFIX)`
line, alongside the existing `discovery_searches`/`discovery_jobs`/
`discovery_runs` includes.

**One-line addition to `backend/app/discovery/providers/manual_csv.py`:**
override `provider_name()` to return `"Manual / CSV Import"` (currently
falls back to the base class default, which is just `self.key` =
`"manual_csv"`). This keeps the backend's own display name consistent
with the label the frontend has hardcoded since M1, so the frontend can
simply render `provider.name` from the new endpoint instead of
maintaining a second, parallel label map. **Flagging this explicitly as
production code (not test code) for approval**, even though it's a
one-line, side-effect-free override of an extension point Phase 2
itself added — it changes what `ManualCSVProvider.provider_name()`
returns, which is new observable behavior, however small.

### 2b. Frontend: dynamic provider list on the Search form

**File:** `frontend/src/pages/DiscoverySearches.tsx`.
- Delete the hardcoded `AVAILABLE_PROVIDERS` constant (line 60).
- Add a `providers: DiscoveryProvider[]` state, fetched once alongside
  the existing `Promise.all([...])` in `load()` (one more parallel
  `apiClient.get("/discovery-providers")` call - this endpoint is
  intentionally NOT company-profile-scoped, so it's fetched once, not
  re-fetched per `companyId` change, though re-fetching on every load
  call is harmless and keeps the code simple; no strong reason to
  special-case it).
- Render the provider checkboxes from this fetched list instead of the
  constant. Each checkbox label becomes `provider.name`. Each gets a
  small health dot: `<StatusIndicator kind={provider.enabled ? "success" : "idle"} label="" />`
  or, more simply given `StatusIndicator` always renders a label,
  reuse `Badge` instead — `<Badge tone={provider.enabled ? "success" : "neutral"}>{provider.enabled ? "Ready" : "Not configured"}</Badge>`
  next to the checkbox label. (Decision needed - see "Open UI choice"
  below.)
- A disabled provider (`enabled: false`) gets its checkbox `disabled`
  too, with the same `Badge` explaining why (e.g. "Not configured") -
  this is Priority 1's exact same honesty principle applied to
  providers: don't let a user select a provider that will just fail the
  job. This also removes the need for `handleRun`'s current
  `manual_csv`-specific validation to be duplicated per-provider later;
  it stays scoped to `manual_csv`'s own row-table requirement, unrelated
  to this change.

### 2c. Frontend: static "Coming Soon" providers

Add a small, static, frontend-only array in the same file:

```tsx
const COMING_SOON_PROVIDERS = [
  "OpenCorporates", "Europages", "TradeIndia", "Alibaba", "Kompass",
];
```

Rendered as visually disabled entries (same checkbox-disabled treatment
as an unhealthy real provider, but with a distinct `Badge tone="neutral"`
reading "Coming soon" rather than "Not configured" - the two states
mean different things and shouldn't look identical: one is "this could
work today if configured," the other is "this doesn't exist yet").
**Deliberately no backend concept for these** - inventing a
"planned provider" registry entry for code that doesn't exist would be
over-building for a roadmap teaser, per the earlier review's own
conclusion.

### 2d. Frontend: provider badges on Prospects

**File:** `frontend/src/pages/Prospects.tsx`.
- Add `sources: ProspectSource[]` to the local `Prospect` interface,
  where `ProspectSource = { provider_key: string }` (only the field
  actually rendered - `ProspectSourceRead` has more fields, but this
  page doesn't need `source_url`/`discovered_at`/etc. for a badge). No
  backend change - `ProspectRead.sources` is already returned by
  `GET .../prospects` today (`app/schemas/prospect.py` line 77); the
  frontend type just needs to stop dropping it.
- Render one small `Badge tone="neutral"` per **distinct**
  `provider_key` found in `prospect.sources` (a prospect re-sighted by
  both `manual_csv` and `brave_search` shows both badges - this is the
  concrete, visible proof that Phase 2's cross-provider dedup actually
  worked, not just a passing test), placed next to the existing status
  badge at line ~295.
- Label text: reuse the SAME title-casing fallback already implemented
  (but currently module-private) in
  `frontend/src/discovery/useDiscoveryExecution.ts`'s `providerLabel()`
  function - export it from there and import it here, rather than
  writing a second copy. This guarantees an unrecognized future
  `provider_key` still renders sensibly (title-cased, underscores as
  spaces) instead of looking broken, matching that function's own
  documented principle ("an unrecognized future provider_key still
  renders... rather than being silently dropped").

### 2e. Frontend: provider badges on Discovery Jobs

**File:** `frontend/src/pages/DiscoveryJobs.tsx`.
- Add a row of small `Badge`s at the top of each job card (next to the
  existing status `Badge` at line 102), one per entry in
  `job.provider_runs`, colored by that run's own `status`
  (`completed`→success, `failed`→danger, `cancelled`→neutral - reusing
  the SAME `STATUS_TONES` map this file already defines for the job's
  own overall status, since the vocabulary is identical).
- Label: `providerLabel(pr.provider_key)` (same shared helper as 2d).
- Keep the existing detailed per-provider text block (duration/request
  count/cost/tokens) exactly as-is, unchanged, immediately below the new
  badge row - the badges are for at-a-glance scanning, the existing text
  stays for anyone who wants the detail. No data already fetched needs
  to change; `job.provider_runs` is already in the response.

### Open UI choice needing a decision before implementation

For 2b's provider health indicator, `Badge` (colored pill) and
`StatusIndicator` (dot + label, per Design Bible Section 5's "color is
never the only signal" rule) are both legitimate design-system
primitives here. `StatusIndicator` is arguably the more "correct" fit
per its own docstring (it's specifically the state-vocabulary
component), but it renders a `label` string as a REQUIRED prop
alongside the dot, which is slightly more visual weight in a checkbox
row than a small `Badge`. I'd lean toward `Badge` for this specific
spot (tighter, matches how `Prospects.tsx`/`DiscoveryJobs.tsx` already
use `Badge` for compact inline status), but will follow whichever the
CEO/design review prefers - flagging rather than deciding unilaterally
since this is a real, if small, design-system usage question.

---

## Priority 3 — Search Depth: informational, not disabled

**Recommendation (restated from the prior review, now finalized):**
keep all three Search Depth options selectable (unlike Search
Frequency, choosing "Deep" isn't an active false promise the way
choosing "Daily" is - it currently does exactly what "Quick" does,
which is a *different*, milder honesty problem than a setting that
silently never fires at all).

**File:** `frontend/src/pages/DiscoverySearches.tsx`, inside the
"Search depth" `Field` (line 299-304). Add one caption line directly
below the `<Select>`:

```tsx
<Field label="Search depth">
  <Select ...>...</Select>
  <p className="mt-1 text-xs text-slate-500">
    Not yet used to vary search scope — informational only for now.
  </p>
</Field>
```

`Field`'s `children` prop is a plain `ReactNode` (confirmed by reading
`frontend/src/components/FormSection.tsx`), so this needs no change to
that shared component - just an extra child element in this one call
site.

**Why not disable Search Depth like Search Frequency:** disabling would
imply "you cannot use this yet," which overstates the problem - a user
CAN select any of the three values today, submit the form, and run a
search successfully; the value is simply inert. Search Frequency's
"Daily" is different: selecting it implies an ongoing commitment
("this will keep running without me") that the system silently fails to
honor at all. The caption approach is honest about "this doesn't do
anything yet" without blocking a choice that isn't actually harmful to
make.

**Risk:** none - captions only, no behavior change, `search_depth`
already defaults to `"standard"` and flows through unchanged.

---

## Priority 4 — Automation: explicitly out of scope

Confirmed not implementing scheduling, recurring jobs, retry handling,
timezone support, or API cost management in this pass. Priority 1's
disabled-option treatment is the ENTIRE product surface this plan
touches for Search Frequency. When a real "Search Scheduling &
Automation" milestone is scoped later, Priority 1's change is a
one-line revert (remove `disabled`) plus whatever real backend work
that milestone needs - it does not need to be un-done or reworked, it's
additive-compatible with turning the feature on for real later.

---

## Suggested build order

1. **2a** (backend endpoint + registry accessor + `manual_csv.py`
   `provider_name()` override) — the one piece everything else in
   Priority 2 depends on.
2. **2d, 2e** (Prospect/Job provider badges) — pure frontend, zero
   dependency on 2a, can genuinely be built and shipped independently/
   first if preferred, since the data these read is already in today's
   API responses.
3. **2b, 2c** (dynamic provider list + health badges + coming-soon
   list on the Search form) — depends on 2a.
4. **Priority 1** (Search Frequency disable) and **Priority 3** (Search
   Depth caption) — both trivial, no dependencies, can land anytime;
   bundling them with 2b/2c's own edit to the same file
   (`DiscoverySearches.tsx`) is the most efficient sequencing since all
   four touch that one file's same form section.

## Testing plan

- Frontend: no existing automated frontend test suite was found to
  extend for `DiscoverySearches.tsx`/`Prospects.tsx`/`DiscoveryJobs.tsx`
  (this project's test coverage is backend-only, per every prior
  milestone's own verification scripts) - verification here will be
  `tsc`/build-clean (matching M8.6/M8.7's own precedent of `tsc` as the
  frontend correctness gate) plus a manual click-through checklist in
  the verify script, same as this project's standing convention for
  frontend-only changes.
- Backend: a new `tests/test_discovery_providers_route.py` for the one
  new endpoint - list shape, `enabled` reflecting `health()` correctly
  for both a configured and unconfigured `brave_search`
  (`BRAVE_SEARCH_API_KEY` set/unset via `monkeypatch`/direct settings
  mutation in the test), and confirming a completely broken/unimportable
  provider key degrades to `enabled: false` rather than a 500. This is
  the one place in this plan with real backend logic worth a real test.

---

## Summary of what touches production backend code

Exactly three small, additive items, all explicitly called out above
for approval:
1. `list_registered_provider_keys()` added to `registry.py`.
2. `provider_name()` override added to `manual_csv.py`.
3. One new route file + one new schema file + one new `include_router`
   line in `main.py`.

Nothing else changes: no provider's `search()`/`health()`/
`capabilities()` behavior changes, no migration, no scheduling, no
change to how a Discovery job actually executes.

Awaiting approval before writing any code.
