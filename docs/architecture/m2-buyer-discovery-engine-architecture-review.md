# M2 — AI Buyer Discovery Engine: Architecture Review

**Status: architecture review only. No implementation. Nothing here is
authorized to be built until explicitly approved, per this project's
standing discipline (see `docs/architecture/README.md`'s own
conventions).**

## 0. A naming discrepancy worth surfacing before anything else

The CEO's brief labels this milestone **M2**. Every existing file in
this codebase that already implements Buyer Discovery — `discovery_job.py`,
`discovery_search.py`, `dedup.py`, `prospect.py`, and the root
`docs/architecture/README.md`'s own canonical milestone list — calls it
**M1** ("`M1 Buyer Discovery Engine`", with "`M2 AI Research & Prospect
Intelligence`" as the *next* milestone after it). This review uses the
CEO's "M2" label throughout to match this conversation, but quotes
existing code comments verbatim where relevant, which will say "M1" —
that is the same system, not a different one, and not a typo on either
side. Worth knowing so a future reader isn't confused cross-referencing
this document against the code.

## 1. The single most important finding

**The Buyer Discovery Engine already exists, is architecturally mature,
and gets most of this brief's design goals right — except the one thing
the brief opens with.** `docs/architecture/README.md` line 140 already
describes three Command Center capabilities as "aggregation/synthesis
endpoints over data M2/M3/M6 already built" — Discovery is real,
load-bearing infrastructure other milestones already depend on, not a
blank slate.

But: **the only registered provider today is `ManualCSVProvider`** —
literally a form where a human pastes or types company name/website/
country/industry/description rows by hand
(`frontend/src/pages/DiscoverySearches.tsx`:
`AVAILABLE_PROVIDERS = [{ key: "manual_csv", label: "Manual / CSV Import" }]`).
There is no Google, Bing, Brave, Europages, Kompass, ImportYeti,
government-registry, or trade-fair provider. "Find textile importers in
Germany" and have the system go find them is **not possible today** — a
user must already know the company names before Discovery can do
anything with them. This is the gap this review centers on; everything
else below is comparatively minor tuning.

The rest of this document works through the CEO's ten design questions
in order, each split into **What exists today** (file-referenced, so it
can be verified against real code) and **Review / what's missing or
weak**.

---

## 2. Design Task 1 — Discovery Job architecture

### What exists today

A genuinely complete job/history model, split across four tables:

- **`DiscoveryJob`** (`app/models/discovery_job.py`) — one execution:
  status (`pending`/`running`/`completed`/`partially_completed`/`failed`/
  `cancelled`), `started_at`/`finished_at`, `providers_used`,
  `raw_result_count`, `prospect_created_count`/`prospect_matched_count`/
  `prospect_qualified_count`/`prospect_rejected_count`, `error_message`,
  a per-provider `log` JSONB array. This already matches the brief's
  example shape (workspace/status/progress/providers/started/finished/
  results/imported/failed) almost field for field.
- **`DiscoveryJobProviderRun`** — one row per provider per job: timing,
  request count, `api_cost` (`Numeric`, not `Float` — a deliberate,
  correct choice for a real cost figure), `token_usage`, status, error.
- **`DiscoveryProviderResult`** — append-only staging: every raw hit a
  provider returned, `raw_payload` preserved byte-for-byte, plus a
  `normalized_payload` and `dedup_key`, linked to whichever `Prospect`
  it resolved into (`matched_prospect_id`). This is exactly what
  "preserve raw provider data for future AI enrichment" needs
  structurally.
- **`DiscoveryRun`** — a frozen, permanent audit snapshot: exact
  `config_snapshot` (template, ICP version, providers, depth) at the
  moment of execution, `prospects_found_count`/`new_prospects_count`/
  `duplicate_count`. Its own docstring is explicit about the split:
  *"DiscoveryJob tracks operational status while it's/just-after
  running... DiscoveryRun is what the review/audit UI reads afterwards."*
- **`ProspectTimelineEvent`** and **`ProspectSource`** add a third and
  fourth layer of history at the individual-prospect level: every
  status change, every provider occurrence, timestamped and attributed.

Execution is reachable two ways: synchronously in-request (early
milestone shape) and — since M8.8 — asynchronously through the M7
Workflow Engine (`POST .../discovery-searches/{id}/run` publishes an
Event, the Event Dispatcher creates a `WorkflowInstance`, the Step
Runner invokes `DiscoveryExecutionAction`, which calls the exact same
`run_discovery_search()` function). `run_discovery_search()` itself
commits incrementally — after job creation, after each provider
finishes, and at final completion — each paired with a
`discovery_job.progress` Event, so a live UI polling
`GET .../discovery-jobs/{id}` sees real, incremental progress rather
than one atomic write at the end.

### Review: resumable / cancellable / history?

- **History: yes, already excellent.** Four complementary layers
  (job/provider-run/raw-result/run-snapshot) plus per-prospect timeline —
  this is not something to redesign, only to extend.
- **Cancellable: no, despite looking like it should be.** `DiscoveryJobStatus`
  already has a `CANCELLED` member, but nothing in the codebase ever sets
  it — there is no `POST .../discovery-jobs/{id}/cancel` route
  (`app/api/routes/discovery_jobs.py` only has `list`/`get`), and
  `run_discovery_search()` has no cancellation checkpoint inside its
  provider loop even if one existed. **This is a real gap, not an
  oversight to leave alone** — once real network-calling providers exist,
  a single provider call can legitimately hang or run long, and a user
  needs a way to stop a job without waiting it out or restarting the
  container.
- **Resumable: partially, and this needs a real decision, not an
  assumption.** A provider that fails mid-job is logged and the job
  moves on to the next provider — the job as a whole is
  fault-*tolerant*. But there is no "resume this specific job from where
  it left off" or "retry only the failed provider" action. At
  100–100,000-result scale (Design Task 9), a job that dies at result
  40,000 of 100,000 re-running from zero is expensive and, for a
  paid-per-request provider, costly. **Recommendation: design (not yet
  build) an explicit `retry_failed_providers` action on `DiscoveryJob`,
  scoped to re-running only the providers whose `DiscoveryJobProviderRun.status
  == "failed"`, writing a new job row that references the old one
  (`resumed_from_job_id`) rather than mutating history in place** — keeps
  the "DiscoveryRun is a frozen, permanent record" guarantee intact while
  giving a real resume path.

---

## 3. Design Task 2 — Provider Framework

### What exists today

`app/discovery/providers/base.py` is a clean, minimal ABC:

```
DiscoveryProvider (ABC)
  key: ClassVar[str]
  search(query_spec: dict, context: DiscoveryContext) -> ProviderSearchOutcome
```

Plus a plain dict registry (`app/discovery/providers/registry.py`,
`get_provider(key)`), the identical shape this project already uses for
email delivery providers (`app/delivery/providers/base.py`'s
`EmailConnectionProvider`/capability-mixin pattern) — this is a proven,
repeated pattern in this codebase, not a one-off. Adding a provider is,
by design, "an import + a dict entry — no schema change, no change
anywhere else in the pipeline" (the registry module's own docstring).
`DiscoveryContext` (assembled once per job: `company_profile`, `icp`,
`products`, `knowledge_base_entries`) is handed uniformly to every
provider, so a provider never needs to know how to fetch its own
targeting data.

### Review

**The interface design itself is sound and should not be redesigned.**
The gap is entirely that only one implementation exists
(`ManualCSVProvider`). A few things worth deciding explicitly before
real providers are built, though, since they'll be awkward to retrofit
across many providers later:

- **`query_spec` is currently schema-less by convention, not by
  contract.** `ManualCSVProvider` reads `query_spec["rows"]`; a Google/
  Bing/web-search-style provider would need something entirely
  different (keywords, target country, industry terms, pagination
  token). Nothing stops each provider from inventing its own
  `query_spec` shape today, which is fine for one provider but will
  make `DiscoverySearch.query_spec`/`SearchTemplate.query_spec` (both
  already schema-less JSONB, by design) hard to validate or build a
  shared UI for once there are five providers with five different
  expectations. **Recommend a thin, optional, provider-independent
  "standard query" shape** (keywords, target countries, target
  industries, target buyer types, company-size hints) that the
  Discovery Engine builds automatically from ICP + Products (see
  Section 9 below — this is the actual fix for "user should not have to
  manually enter company names"), which providers may additionally
  supplement with a provider-specific override block. Each provider
  still decides how to *use* the standard shape; they don't have to
  agree on internals.
- **Rate limiting / cost ceilings are not modeled anywhere.** A real
  search-API provider (Google Custom Search, Bing, Kompass) has a hard
  request quota and often a per-request cost. `DiscoveryJobProviderRun.api_cost`
  already *records* cost after the fact, but nothing enforces a ceiling
  before or during a run. Worth a per-provider (or per-ICP) configurable
  cap before real paid providers are wired in.
- **No provider health/circuit-breaker concept.** If a provider's API
  key expires or its endpoint starts 500ing, today's behavior is: every
  job that enables it logs a failure and moves on, forever, silently
  wasting a request each time. Contrast with the Delivery domain's
  `ProviderConnection.status` (`CONNECTED`/`EXPIRED`/`ERROR`) — Discovery
  has no equivalent "this provider is currently unhealthy, skip it
  without even trying" gate. Worth adopting the same pattern once a
  provider has persistent credentials (see also Design Task 2's
  "government registry"/"trade fair" providers, which likely need
  their own API keys, i.e. their own `ProviderConnection`-style
  credential record — reusing the Delivery domain's existing
  credential-store infrastructure rather than inventing a second one).

---

## 4. Design Task 3 — Candidate Collection

### What exists today

`RawProviderResult` (`app/discovery/providers/base.py`) is already a
unified model, close to field-for-field with the brief's list:

| Brief's field | Existing field |
|---|---|
| Company Name | `name` |
| Website | `website` |
| Country | `country` |
| Industry | `industry_raw` |
| Description | `description` |
| Source | `source_url` (+ the provider's own `key`, recorded separately per result) |
| Confidence | `provider_confidence` |

Plus fields the brief didn't list but the current model already needs:
`company_size_range`, `raw_payload` (the untouched original, for future
AI re-processing), and `contacts: list[RawContactResult]` (people found
alongside the company).

### Review

This is solid and matches the brief's intent almost exactly. Two real
gaps:

- **No VAT number / registration number field anywhere** — not on
  `RawProviderResult`, not on `Prospect`. The brief explicitly names
  these as dedup signals (Design Task 4), and a government-registry
  provider (one of the eight example providers named in the brief) would
  almost certainly surface exactly this data. Needs a schema addition
  when that provider is built — flagged now so it isn't missed.
- **No structured `industry` targeting on the candidate side beyond a
  single free-text field.** `industry_raw` is a string; there's a
  resolved `Industry` reference table (`app/models/industry.py`) with an
  `industry_id` FK on `Prospect`, but nothing in `RawProviderResult` or
  the pipeline attempts to resolve `industry_raw` onto the reference
  table automatically (that resolution, if it happens at all today,
  isn't visible in `pipeline.py` — it stays `industry_raw` forever
  unless something else sets `industry_id`, which appears to be nothing
  yet). Worth deciding whether industry resolution is a deterministic
  keyword-match step (cheap, explainable, consistent with the rest of
  M2's philosophy) or deferred to Research/AI enrichment (M3 in this
  codebase's numbering) — but a decision either way, not silence.

---

## 5. Design Task 4 — Deduplication

### What exists today

`app/discovery/dedup.py` — two-tier, deliberately not fully automatic in
the ambiguous band:

- **Definite match:** normalized website equality (strips `http(s)://`,
  `www.`, trailing slash, lowercases) → `confidence=1.0`, auto-merged
  (updates `last_seen_at`, does not create a new `Prospect`).
- **Potential match:** fuzzy name similarity (`difflib.SequenceMatcher`
  on a normalized name — legal suffixes like Ltd/GmbH/Inc stripped,
  non-alphanumeric collapsed) plus a country equality check, banded
  between 0.6 and 0.85 → flagged `ProspectStatus.DUPLICATE_REVIEW` with
  `potential_duplicate_of_prospect_id` and `duplicate_confidence` set,
  for a human to resolve, never silently merged.
- Below 0.6: treated as a genuinely distinct company.

### Review

The two-tier, human-in-the-loop-for-the-ambiguous-band design is the
right call and shouldn't change — silently merging two genuinely
different companies because their names are 70% similar would be a
worse failure mode than asking a human once. Two real gaps, both
consequences of the same underlying cause (Design Task 3's finding):

- **Only two signals are used (domain, fuzzy name+country) out of the
  five the brief names.** No VAT number, registration number, or email
  matching exists, because none of those fields exist on `Prospect` or
  `RawProviderResult` today (see Design Task 3). This isn't a dedup-logic
  gap so much as a data-model gap upstream of it — VAT/registration
  number are the *strongest possible* dedup signal (a government
  business ID is definitionally unique; a fuzzy name match never is),
  and should be checked *before* falling back to fuzzy matching once
  available, not as a third tier alongside it.
- **`find_duplicate()` is O(n) against every prospect the business has
  ever discovered, held entirely in Python memory for the whole job**
  (`existing_prospects = list(db.scalars(...).all())` in
  `pipeline.py`). At the scale the brief asks about (Design Task 9 —
  10,000–100,000 results), this is a real, concrete performance risk,
  not a hypothetical one — see Design Task 9 below.

---

## 6. Design Task 5 — AI Research separation

### What exists today

Already correctly separated, and this needs no redesign at all.
Discovery (`app/discovery/`) never imports anything from Research
(`app/research/`) or vice versa. Research runs against **one specific,
already-existing `Prospect`** (`ResearchContext.prospect` — its own
docstring: *"prospect is the one thing Discovery's context never
needed — Discovery searches for prospects; Research always enriches one
specific, already-existing prospect"*), triggered by its own explicit
`ResearchRequest` + `ResearchExecutionAction` through the same M7
Workflow Engine pattern as Discovery — never invoked automatically from
inside `run_discovery_search()`. A prospect can sit fully unscored-by-AI
indefinitely; nothing forces enrichment to happen at discovery time.

### Review

No changes needed here. This is exactly the boundary the brief asks
for, already built, already proven by two other milestones (M3
Personalization, M4 Outreach, in this codebase's numbering) consuming
Research's output the same event-driven way. Worth explicitly
confirming to the CEO that this is *not* a gap — it would be a mistake
to "fix" something that already works.

---

## 7. Design Task 6 — ICP Matching (Explainable)

### What exists today

`app/discovery/scoring.py` — deterministic (no LLM call), genuinely
explainable, four independently-computed factors, each contributing a
dict with `factor`/`weight`/`matched`/`points`/`explanation`:

| Factor | Weight | What it checks |
|---|---|---|
| `buyer_type_match` | 25 | `Prospect.buyer_type_id` in `ICPCriteria.target_buyer_types` |
| `market_match` | 25 | `Prospect.country` in `ICPCriteria.target_markets`; explicit exclusion list force-disqualifies regardless of every other factor |
| `company_size_match` | 20 | `Prospect.company_size_range` in `ICPCriteria.preferred_company_size` |
| `product_keyword_relevance` | 30 | keyword/application overlap between the business's `Product` catalog and the prospect's free-text `description` |

Weights sum to 100. A missing/unset ICP dimension is treated as "no
preference" (full credit), not as a failure — an explicit, sensible
default, and itself explained (`"ICP specifies no target buyer types -
treated as no preference."`).

### Review: this is the closest thing in this codebase to already
### matching the brief's ask exactly

Four of the five factors the brief names exist, each independently
scored and explained. **The one missing factor is Industry Match** —
and it's missing for a real, traceable reason: `ICPCriteria` has no
`target_industries` relationship at all (`app/models/icp_criteria.py`
has `target_buyer_types`/`target_markets`/`excluded_countries`/
`languages`, no industries), even though the `Industry` reference table
already exists and is already used elsewhere (`CompanyProfile.industries`
— the seller's own industries; `Prospect.industry_id`/`industry_raw` —
the discovered company's industry). The pieces exist; they were never
connected for ICP targeting.

**Recommended fix (design only, not yet built):** add
`ICPCriteria.target_industries` (a junction table, same shape as
`icp_criteria_target_buyer_types`), rebalance the four existing weights
to make room for a fifth (e.g. 20/20/20/15/25, or let the CEO set the
actual split), and add `_score_industry()` to `scoring.py` following the
exact same pattern as `_score_buyer_type()` — this is a small, additive,
low-risk change once approved, not a rewrite.

One more thing worth deciding explicitly rather than leaving implicit:
**weights are hardcoded module constants today, not configurable per
ICP or per business.** `ICPCriteria.weight` exists as a column
(currently a single float, default 1.0 — an overall ICP weight, not a
per-factor breakdown) but nothing reads it inside `scoring.py`. Whether
per-factor weights should become CEO/user-configurable per ICP (more
flexible, more UI surface) or stay fixed platform-wide constants
(simpler, consistent scoring across every business) is a real product
decision, not an implementation detail — flagging it rather than
assuming an answer.

---

## 8. Design Task 7 — Explainability

### What exists today

Already the pattern the brief describes almost verbatim.
`Prospect.score_breakdown` is a JSONB list of exactly
`{factor, weight, matched, points, explanation}` objects — never a bare
number. `Prospect.total_score` is the sum, but it is never presented
without `score_breakdown` alongside it in the data model (both columns
live on the same row). `Prospect.ai_reasoning` (currently always `null`)
is a reserved column for a *future* narrative pass — the intent already
recorded in the model's own docstring: *"Narrative justification from a
future AI scoring/reasoning pass. Column exists from day one; stays
null until that milestone exists."*

### Review

Nothing to fix. This already satisfies "never output a score without
reasons" at the data-model level. The brief's example format (a
checklist of ✓ reasons followed by a final percentage) is a
**presentation** question, not an architecture question — the
underlying `score_breakdown` array already has everything a frontend
would need to render exactly that checklist (each entry's `matched:
true` + `explanation` *is* one ✓ line; `matched: false` or `null` is
where it isn't). No backend change needed to support that UI; this is
worth noting so a future frontend milestone doesn't assume it needs new
API surface for something that already exists.

The one real design question: **should `ai_reasoning` ever *replace*
`score_breakdown`, or only ever sit alongside it as a narrative
summary?** Given the brief's own instruction ("never output a score
without reasons"), the deterministic `score_breakdown` should remain the
source of truth and stay visible even after an AI narrative exists —
`ai_reasoning` should be an additional narrative *derived from*
`score_breakdown`, never a replacement that could drift from or
contradict the actual factor-level math. Worth stating as an explicit
constraint now, before an AI-reasoning milestone is designed, so it
isn't discovered as a disagreement later.

---

## 9. Design Task 8 — Prospect Import

### What exists today

**Does not exist.** `Prospect`'s own docstring is explicit and
unambiguous: *"This is Discovery's own entity — entirely separate from
the CRM's Company — and stays that way until a future milestone's
explicit, one-way import action creates a Company from an approved
Prospect. M1 does not implement that import; only Approve/Reject/
Archive exist here."* `app/api/routes/prospects.py` confirms this: only
`approve`/`reject`/`archive` actions exist, nothing that creates a
`Company`, `Contact`, or (per the newer Opportunity domain) an
`Opportunity`.

`ProspectContact`'s field set was deliberately shaped to make this easy
later — its own docstring: *"Field set deliberately mirrors the CRM's
Contact model closely... so a future CRM-import routine can map each one
onto a real Contact with no translation logic."* The intent was always
there; the action itself was never built.

Separately: the legacy `Company`/`Contact` models are themselves
mid-deprecation (per `deferred-items-and-design-boundaries.md`, "Phase 1
deprecation markers complete; Phase 2 removal is future work") — so
"import into Company/Contact" needs to be designed against **whatever
the CRM's real, current entity is by the time this is built**, not
against a model already flagged for removal.

### Review

This is the second largest concrete gap after real providers, and it's
one the brief explicitly asks about. Recommended design (not yet
built):

- **A single, explicit, one-way action** — e.g.
  `POST .../prospects/{id}/import` — callable only on an `APPROVED`
  prospect (never `NEW`/`UNQUALIFIED`/`DUPLICATE_REVIEW` — approval
  must happen first, matching the existing "human decides, then the
  system acts" discipline already used everywhere else in this
  project, e.g. Task complete/dismiss, OutreachDraft approve/reject).
- **Idempotent and dedup-aware against the CRM side, not just the
  Discovery side.** A `Prospect` that's already been imported once
  (e.g. re-approved after being re-discovered) must not create a
  second Company/Opportunity — needs its own "already imported" marker
  (e.g. `Prospect.imported_at` / `imported_company_id`), mirroring the
  same "never silently duplicate" principle Design Task 4 already
  applies on the Discovery side.
- **Scope the import target now, correctly, given the legacy
  deprecation:** given `Company`/`Contact` are being phased out and this
  project already has a real `Opportunity` domain (Track C3), the
  natural destination is likely `Opportunity` (+ whatever the CRM's
  current non-legacy contact entity is) rather than the deprecated
  `Company`/`Contact` pair — worth an explicit decision before writing
  any import code, so this isn't built against a model already
  scheduled for removal.
- **No CRM writes as a side effect of Discovery/Research/scoring** —
  this already matches a rule this project has stated elsewhere
  (Mailbox Brief's own design constraint: *"no CRM writes as a side
  effect... even though the Opportunity model now exists, [a
  process] must never auto-create one; that stays a separate, explicit
  user action"*). The same rule should apply here: scoring a prospect
  QUALIFIED must never itself create an Opportunity; only the explicit
  import action does.

---

## 10. Design Task 9 — Scalability

### What exists today

Per-provider execution metrics (`DiscoveryJobProviderRun`: duration,
request count, cost, token usage) are already tracked, suggesting the
data model was built with future parallelism/cost-awareness in mind.
Incremental commits (one per provider, not one atomic write) already
mean a live viewer sees real progress on a long-running job.

**However, actual execution today is strictly sequential and
single-instance:** `run_discovery_search()` is one Python function, one
`for provider_key in search.provider_keys` loop, run by one single Step
Runner worker invocation. No provider runs concurrently with another
within the same job. And as noted in Design Task 4, `find_duplicate()`
loads **every existing prospect the business has ever discovered** into
Python memory for every single job, checked in an O(n) linear scan per
new result — meaning total dedup cost per job is roughly
O(existing_prospects × new_results).

### Review — this is the area most likely to break first at real scale

Concretely: at 100 results this is invisible. At 10,000 it will be
noticeably slow. At 100,000 (the brief's own upper bound), a
single-threaded, in-memory-dedup, one-worker-instance design will
likely time out, exhaust memory, or both, and there is currently no
architectural mitigation in place — this needs real design work, not
optimism, before a job of that size is attempted. Recommendations for
the actual implementation phase (not now):

- **Parallelize providers within a job.** Nothing about the current
  `DiscoveryProvider` interface prevents this — each provider's
  `search()` call is already independent and stateless with respect to
  the others. The blocker is purely in `run_discovery_search()`'s
  sequential loop, not the provider contract itself.
- **Move dedup off "load everything into memory."** A real,
  indexable lookup (the existing `dedup_key` column on
  `DiscoveryProviderResult`, or a proper Postgres index on normalized
  website/name rather than a Python-side `SequenceMatcher` scan) will be
  necessary once the per-business prospect count gets large — this is
  exactly the kind of problem `dedup.py`'s own docstring already
  flags: *"small enough set for this to be fine at M1's scale"* (i.e.
  already disclosed as a known, deliberately-deferred limitation, not a
  surprise).
- **Chunk/paginate large result sets rather than one job holding
  100,000 raw results in a single transaction's working set.** Given
  Design Task 1's incremental-commit pattern already exists per-provider,
  extending it to commit in bounded batches *within* one provider's
  result set (not just between providers) is a natural, additive
  extension of the same mechanism, not a new one.
- **Research should run asynchronously and separately from Discovery
  regardless of scale** — already true today (Design Task 5), and this
  property becomes more important, not less, as Discovery volume grows:
  Discovery must never be gated on Research's (potentially much slower,
  AI-call-bound) throughput.

---

## 11. Design Task 10 — Future Compatibility (M3–M8.5)

### What exists today

This is the **strongest** part of the existing architecture and
deserves to be highlighted, not just audited for gaps. The M7 Workflow
Engine (Event → WorkflowInstance → Action) already IS the clean,
decoupled API surface the brief asks for:

- Discovery publishes `discovery_search.run_requested` and
  `discovery_job.progress` Events — any future module can subscribe to
  either without Discovery knowing they exist.
- `DiscoveryExecutionAction` demonstrates the exact integration shape a
  future module would follow: no tight import of Discovery internals,
  only `WorkflowInstance.subject_type`/`subject_id` plus the Event's own
  `actor_type`/`actor_id` for attribution.
- This same pattern is already proven across three other milestones —
  Research, Personalization, and Outreach are each wired into the M7
  engine the identical way (per this project's own implementation
  history), not a one-off for Discovery.

### Review

No redesign needed. The one thing worth stating explicitly for the
record: **every future consumer (Research, Personalization, Outreach,
Reply Intelligence, Workflow Automation, AI Workspace) should keep
reading Discovery's results the same way — through `Prospect`/
`ProspectContact`/`score_breakdown`/Events — never by reaching into
`DiscoveryProviderResult.raw_payload` directly.** The raw payload exists
for audit/future-reprocessing, not as a stable contract a downstream
module should depend on; `Prospect`'s normalized, already-deduplicated,
already-scored fields are the real interface. Worth writing down now,
before a future milestone is tempted to reach past the intended
boundary for one field it thinks is faster to grab directly.

---

## 12. Proposed data flow (current + gap-closing additions)

```
Workspace + Company Profile + Products + ICP Criteria (existing)
        │
        ▼
DiscoverySearch (existing) ── query_spec built FROM ICP/Products/Industries/
   │                          Countries/BuyerTypes, not typed by a human
   │                          [NEW — closes the "must define WHAT, not
   │                           WHO" gap]
   ▼
DiscoveryJob (existing) ──► for each enabled provider (existing, sequential
   │                        today; PARALLEL — proposed, Design Task 9):
   │
   ├─► DiscoveryProvider.search() [existing interface]
   │     ├─ ManualCSVProvider (existing, only real implementation today)
   │     └─ Google / Bing / Brave / Europages / Kompass / ImportYeti /
   │        Government Registry / Trade Fair providers [NEW — the core gap]
   │
   ▼
RawProviderResult (existing unified model) ──► DiscoveryProviderResult
   │  (existing: raw_payload preserved, normalized_payload computed)
   ▼
Dedup (existing: website + fuzzy name/country;
        VAT/registration/email — NEW, pending Design Task 3/4 schema additions)
   │
   ├─ definite match → update existing Prospect (existing)
   ├─ potential match → new Prospect, status=DUPLICATE_REVIEW (existing)
   └─ no match → new Prospect, status=NEW (existing)
   ▼
Scoring (existing: buyer_type/market/company_size/product_relevance;
          industry_match — NEW, pending ICPCriteria.target_industries)
   │
   ▼
Prospect (existing: score_breakdown always alongside total_score,
           status → QUALIFIED/UNQUALIFIED/DUPLICATE_REVIEW)
   │
   ├─► [existing, unchanged] Research (M2/"M3" — separate, explicit,
   │     per-prospect trigger, never automatic)
   │
   └─► [NEW] explicit Prospect Import action (only from APPROVED) →
         Opportunity (+ current CRM contact entity) — one-way, idempotent,
         never a side effect of scoring/approval alone
```

---

## 13. Required database entities

**Already exist (no change needed):** `DiscoverySearch`, `SearchTemplate`,
`DiscoveryJob`, `DiscoveryJobProviderRun`, `DiscoveryProviderResult`,
`DiscoveryRun`, `ICPCriteria`, `Prospect`, `ProspectContact`,
`ProspectSource`, `ProspectTimelineEvent`, `BuyerType`, `Industry`,
`Country`, `Product`.

**Proposed additions (design only — exact columns/migrations to be
specified at implementation-approval time, not now):**

- `ICPCriteria` ↔ `Industry` junction table (`icp_criteria_target_industries`),
  closing the Industry Match gap (Design Task 6).
- `Prospect` (and/or `RawProviderResult`/`DiscoveryProviderResult`):
  `vat_number`, `registration_number` fields, closing the stronger-dedup-
  signal gap (Design Tasks 3–4).
- `DiscoveryJob.resumed_from_job_id` (nullable, self-referencing) —
  supports the proposed retry-failed-providers action (Design Task 1)
  without mutating history in place.
- `Prospect.imported_at` / `imported_opportunity_id` (or equivalent) —
  supports the proposed one-way Prospect Import action (Design Task 8),
  idempotency guard.
- A credential/health record for providers that need API keys (Government
  Registry, Trade Fair, and likely Kompass/ImportYeti) — reusing the
  Delivery domain's existing `ProviderConnection`/credential-store
  pattern rather than inventing a parallel one (Design Task 2).

---

## 14. Required services (proposed, additive to existing)

- **Query-spec builder service** — turns ICP + Products + Industries +
  Countries + Buyer Types into the "standard query" shape described in
  Design Task 2, so a `DiscoverySearch` can be configured by *defining
  criteria*, never by typing a search string. This is the actual
  architectural fix for the brief's opening objective.
- **Provider credential/health service** — mirrors
  `app/delivery/connection_service.py`'s shape for whichever new
  providers need OAuth/API-key credentials, including a health-check
  gate before a job even attempts a call (Design Task 2).
- **Prospect Import service** — the one-way, idempotent, explicit action
  described in Design Task 8.
- Everything else (pipeline orchestration, scoring, dedup) already
  exists as a service layer today and should be *extended*, not
  replaced.

## 15. Required workers

- **No new standalone worker process is required.** The existing
  Event/WorkflowInstance/Action/Step-Runner-worker substrate already
  handles asynchronous execution (Design Task 10) — a real search
  provider is a new `DiscoveryProvider` implementation called from the
  *same* `run_discovery_search()` pipeline, not a new worker.
- **If/when parallel-provider execution (Design Task 9) is built,** it
  should still run *within* one `DiscoveryExecutionAction` invocation
  (e.g. a bounded thread/async pool for I/O-bound provider calls), not
  as N separate worker processes — keeps the existing single-job,
  single-`DiscoveryJob`-row model intact rather than fragmenting one
  logical job across multiple uncoordinated workers.

---

## 16. Discovery lifecycle (proposed, building on the existing one)

1. Business defines Company Profile, Products, ICP Criteria (existing).
2. Business creates/activates a `DiscoverySearch` bound to a
   `SearchTemplate`, an ICP version, and a set of enabled providers
   (existing) — query construction becomes criteria-driven (proposed).
3. Run triggers a `DiscoveryJob` (existing, both sync and async paths).
4. Each enabled provider searches independently (existing interface;
   proposed: run in parallel, each still producing its own
   `DiscoveryJobProviderRun`).
5. Raw results staged append-only (existing `DiscoveryProviderResult`).
6. Dedup runs against existing prospects (existing website+fuzzy-name;
   proposed: VAT/registration-number as a third, strongest tier).
7. Scoring runs per new/updated prospect (existing four factors;
   proposed: fifth industry factor).
8. Prospect reaches a terminal Discovery status: `QUALIFIED`/
   `UNQUALIFIED`/`DUPLICATE_REVIEW` (existing).
9. Human reviews → `APPROVED`/`REJECTED`/`ARCHIVED` (existing).
10. **[Proposed]** Approved prospect → explicit, one-way Import action →
    Opportunity (+ current CRM contact entity).
11. Research, Personalization, Outreach, Reply Intelligence each
    separately, explicitly triggered off the resulting Prospect/
    Opportunity (existing pattern, Research already proven; the later
    three already consume similarly-shaped data per this project's own
    history).
12. `DiscoveryRun` freezes the whole execution's configuration and
    outcome permanently (existing).

Job-level lifecycle states: `PENDING → RUNNING → (COMPLETED |
PARTIALLY_COMPLETED | FAILED | CANCELLED)` (existing enum; `CANCELLED`
currently unreachable — proposed cancel action, Design Task 1).

---

## 17. Risks

1. **Real provider integrations (Google/Bing/Brave/Europages/Kompass/
   ImportYeti/government registries/trade fairs) are external, rate-
   limited, sometimes paid, sometimes ToS-restricted (scraping vs.
   official API) surfaces this project has zero existing implementation
   experience with** (`ManualCSVProvider` needs no network call at all —
   every real provider will be the first of its kind here). Each one
   should be scoped, approved, and built as its own small track, the
   same discipline already used for the Command Center capability
   tracks (C1–C5) — not all at once.
2. **Scale claims (10k–100k results) are currently unproven** — see
   Design Task 9. Sequential provider execution + full-memory dedup will
   very likely need to change before any real job at that scale is
   attempted; underestimating this risk could mean a job that silently
   never finishes or takes down a worker process.
3. **VAT/registration-number dedup requires a schema change that
   currently doesn't exist anywhere** (not on `Prospect`, not on
   `RawProviderResult`) — needs to land before the providers most
   likely to supply that data (government registries) are built, or
   those providers will ship without their strongest dedup signal
   available.
4. **The legacy `Company`/`Contact` deprecation is mid-flight.** Building
   Prospect Import against the wrong (soon-to-be-removed) target model
   would create rework. This needs one explicit decision (import into
   Opportunity + current contact entity, not legacy Company/Contact)
   before Design Task 8 is implemented.
5. **No provider cost ceiling exists.** A misconfigured or runaway job
   against a paid provider (Kompass, ImportYeti-style paid lookups)
   could generate real, uncapped cost before anyone notices — worth a
   hard per-job or per-ICP spend ceiling before wiring in any paid
   provider.
6. **Explainability's biggest risk is regression, not absence.** The
   current deterministic `score_breakdown` is genuinely good already;
   the risk is a future AI-reasoning pass (Design Task 7) being built in
   a way that *replaces* rather than *supplements* it, quietly losing
   the "always show reasons" guarantee this milestone already has.

---

## 18. Recommended implementation phases

Given how much of this milestone already exists, phases are scoped
around **closing specific, named gaps**, not "building M2 from
scratch." Each phase should go through this project's normal
proposal → approval → implementation → verification cycle
independently, the same discipline as every prior Track.

1. **Phase 1 — ICP Industry Match.** Smallest, most self-contained gap:
   `ICPCriteria.target_industries` junction table + `_score_industry()`
   in `scoring.py` + rebalanced weights. No new provider, no new worker,
   pure extension of already-proven code.
2. **Phase 2 — Dedup signal expansion.** `vat_number`/
   `registration_number` fields on `Prospect`/`RawProviderResult`,
   wired into `dedup.py` as the strongest tier, checked before fuzzy
   name matching.
3. **Phase 3 — Prospect Import action.** The one-way, idempotent
   Approved-Prospect → Opportunity(+contact) action (Design Task 8),
   decided against the *current* (non-legacy) CRM target model.
4. **Phase 4 — First real search provider (one, not eight).** Pick the
   single most valuable provider (likely a general web-search API —
   Google or Bing — since it's the most broadly useful and the least
   likely to have unusual legal/ToS constraints compared to a
   registry/scrape-based source) and build it end to end: query-spec
   construction from ICP/Products, real HTTP integration, credential
   handling, cost tracking. This is the phase that actually delivers
   "the user should not have to manually enter company names" for the
   first time. Treat every subsequent provider as its own follow-on
   phase, not a batch.
5. **Phase 5 — Job cancellation.** Real `CANCELLED` reachability: a
   route + a cancellation checkpoint inside the provider loop. Natural
   to build once Phase 4 introduces a provider whose calls can actually
   take long enough to want to cancel.
6. **Phase 6 — Scale hardening.** Parallel provider execution + dedup
   performance work (indexed lookup instead of full in-memory scan) +
   chunked commits within a provider's result set — deferred until
   there's a real provider (Phase 4) generating enough volume to justify
   and test against.
7. **Phase 7 — Job resume / retry-failed-providers.** Builds on Phase 6's
   execution model; lower priority than the above since today's
   fault-tolerant (if not resumable) behavior is a reasonable interim
   state.

Provider credential/health infrastructure (Design Task 2's
`ProviderConnection`-style pattern) should be built alongside whichever
phase first needs it (likely Phase 4), not speculatively ahead of time.

---

## 19. Summary for approval

What's already real and should not be redesigned: the Job/Run/
ProviderRun/ProviderResult history model, the provider ABC + registry
pattern, the unified `RawProviderResult` candidate model, two-tier
dedup, the Discovery/Research separation, four-factor explainable
scoring, and the Event/Workflow-Engine integration for future-module
compatibility.

What's genuinely missing, in priority order: real search providers
(the central gap), the Prospect → Opportunity import action, a fifth
(industry) scoring factor, stronger dedup signals (VAT/registration
number), and job cancellation.

No code has been written. Waiting for approval on which phase(s) above
to authorize before implementation begins.
