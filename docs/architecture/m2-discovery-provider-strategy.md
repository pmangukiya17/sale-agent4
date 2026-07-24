# M2 — Discovery Provider Strategy

**Status: APPROVED, with two CEO-directed architectural refinements
incorporated (Section 11) — Search Service abstraction and Query
Planner. Implementation proceeds per the consolidated phase order in
Section 10, updated to reflect both refinements. Builds directly on
`m2-buyer-discovery-engine-architecture-review.md`'s conclusion — the
Discovery Engine's core architecture is mature and should not be
redesigned; the gap is that only `ManualCSVProvider` exists.**

This document was researched, not assumed — the provider landscape
changes fast enough (see Section 1) that recommending one from memory
would risk recommending something already dead or dying. Sources are
cited inline; a Sources section closes the document.

---

## 1. First Provider

### The comparison, grounded in current facts

| Option | Current status | Legal/API footing | Fit for "define what you want, not who" |
|---|---|---|---|
| **Bing Search API** | **Retired entirely on August 11, 2025.** Not signupable, not usable, at all, as of today. | N/A — gone | N/A |
| **Google Custom Search JSON API** | **Closed to new customers as of 2025**; existing users can continue only until **January 1, 2027**, then full retirement. Google's own recommended replacement is Vertex AI Search — a different, heavier product. | Official, but a dead end on a fixed clock | Good today, but building the flagship integration on an API with a published shutdown date already inside this project's likely build+run horizon is a foreseeable, avoidable mistake |
| **Brave Search API** | Actively maintained, commercially licensed. ~$5 per 1,000 queries (50 req/s), small monthly free credit, enterprise tier available. | Official API, published commercial ToS, SOC 2 Type II, GDPR-compliant. One real restriction: results may not be used to train/fine-tune/benchmark AI models (not what M2 would do with them); attribution ("Powered by Brave" + logo) must be shown wherever results surface. | Yes — general web search is the only source type here that can answer an open-ended semantic query like *"textile importers in Germany"* directly |
| **Europages** | No official public API. Every available integration found is a third-party scraper (Apify listings etc.) | Scraping a commercial EU directory against its own terms carries real exposure — breach of contract at minimum, and the EU's own sui generis database-rights regime specifically protects directory compilations like this one. Also operationally fragile: breaks on any HTML change, no SLA. | Would be excellent *if* licensed properly — matches "define WHAT you want" less directly than search (still a directory browse, not semantic query), but strong for a defined industry/country combination |
| **Kompass** | Same as Europages — no official public API, scraper-only integrations found. | Same risk profile as Europages | Same as Europages |
| **Government business registries** (e.g. OpenCorporates as an aggregator, or a national registry like Germany's Handelsregister / UK Companies House directly) | OpenCorporates: official commercial API exists; paid tiers start roughly £2,250/yr for the Essentials package, with a genuinely free tier for open-data/open-license use. Published Enterprise API Terms of Service. | **The cleanest legal footing of any option here** — public-record company data with explicit commercial-API terms | Weak fit as a *discovery* source — registries are searched by jurisdiction/registration number/legal name, not by semantic concept like "textile importer." Excellent fit as a **validation/enrichment** source instead (see Sections 2 and 5) |
| **Trade fair exhibitor lists / other structured public sources** | No consistent pattern — varies per organizer, mostly no API | Inconsistent, would need case-by-case legal review per source | Narrow, seasonal, not a general-purpose first choice |

### Recommendation: Brave Search API, not because it's the default, but because it's the last one standing

Explicitly not "Google because it's popular" — the research above shows
Google is actively the *worse* long-term bet of the two general search
APIs: it's already closed to new signups and has a hard retirement date
inside this project's realistic build-and-run window. Bing is simply
gone. That leaves Brave as **the only actively-maintained, officially
licensed, general-purpose web search API left** that can answer an
open-ended query the way the CEO's own founding example demands.

Three reasons this is the right *first* provider specifically (not just
the least-bad option):

1. **It's the only source type that can do semantic discovery at all.**
   Directories (Europages/Kompass) and registries (OpenCorporates) are
   browsed by structured filters the user doesn't necessarily know in
   advance (an industry classification code, a jurisdiction). A search
   API takes the ICP-derived query as-is.
2. **Lowest combined legal + operational risk among the live options.**
   Official API, published ToS, no scraping-fragility exposure —
   materially safer than the Europages/Kompass scraper-only route.
3. **It slots into the existing `DiscoveryProvider` ABC with zero
   engine changes** — one more HTTP-based provider, architecturally
   identical in shape to how `ManualCSVProvider` already plugs in.

**Recommended second provider (not first): OpenCorporates.** Not for
open-ended discovery — for exactly the opposite reason: it's the
authoritative, legally clean source for confirming a company genuinely
exists and for supplying the VAT/registration-number fields the
previous review flagged as a dedup gap. It belongs in the design as
both a future discovery provider *and* — sooner, and more valuably — as
a data source inside the new Validation layer (Section 5).

**Recommendation against Europages/Kompass for now.** Not ruled out
forever, but only ever via a properly licensed data relationship — a
reseller or an official partnership — never a self-built scraper
against their own terms. Flagging this now so it isn't quietly built
later by whoever implements Phase 2/3 without re-litigating the legal
question.

---

## 2. Discovery Strategy — the complete flow for Brave Search

**Updated per Section 11's CEO-directed refinements** — the
Query-Spec Builder below is superseded by the Query Planner, and
providers are no longer called directly by the Discovery Engine; both
are described in full in Section 11. This section keeps the original
end-to-end walkthrough for continuity, with each superseded step
pointing at its replacement.

```
Workspace
  │
  ▼
Company Profile + Products + ICP Criteria
  │
  ▼
Query Planner [Section 11.2 — supersedes the Query-Spec Builder
  │             originally proposed here]
  │  turns ICP targeting (buyer types, industries, countries, product
  │  keywords, languages, synonyms) into a SET of concrete search-query
  │  strings, e.g.:
  │    "textile importer Germany" / "Textilimporteur Deutschland"
  │    "wholesale textile buyer Germany site:.de"
  │  — not one query. See Section 9: this matters a lot at scale.
  ▼
Search Service [Section 11.1 — NEW abstraction layer, sits between the
  │              Discovery Engine and every search provider]
  │  executes the Query Planner's variations against one or more
  │  registered search providers and merges their results before
  │  anything reaches Normalization.
  ▼
BraveSearchProvider.search(query, context)  [NEW provider, existing
  │                                           ABC, now called only by
  │                                           the Search Service, never
  │                                           directly by the Discovery
  │                                           Engine]
  │  issues one Brave Search API call per query variation, retrieves
  │  ranked web results (title, snippet, URL) — NOT already-structured
  │  company records.
  ▼
Candidate Extraction  [NEW — see note below]
  │  turns a web-search RESULT (a page) into a RawProviderResult
  │  (a COMPANY): website = result's domain, name = a heuristic off the
  │  page title (strip common suffixes like "| Home", "- LinkedIn"),
  │  description = the search snippet, country = inferred from
  │  ICP/query context and TLD as a weak signal, confidence = LOW by
  │  default (a search hit is a much weaker signal than a directory
  │  listing or registry record — reflected honestly in
  │  provider_confidence, not inflated).
  ▼
Normalization  [PROPOSED — Section 4]
  ▼
Validation  [PROPOSED — Section 5]
  ▼
Deduplication  [existing engine, extended per the prior review]
  ▼
Candidate Companies (Prospect, status=NEW/DUPLICATE_REVIEW)
  ▼
Scoring → Human review → [existing, downstream]
```

### The important nuance this flow surfaces

A search-engine-based provider is structurally different from a
directory-based one in one specific way worth designing for
deliberately, not discovering by accident later: **a directory listing
(Europages/Kompass/OpenCorporates) already IS one company per row** —
the provider's raw result and the eventual candidate are almost the
same shape. **A web search result is a page, not a company** — turning
it into a candidate requires an extra interpretive step (the
"Candidate Extraction" box above) that a directory provider never
needs.

This raises a real design decision, flagged here rather than assumed:
should Candidate Extraction be **lightweight** (snippet/title/domain
heuristics only, as sketched above — fast, cheap, no extra network
call) or **heavy** (fetch the landing page, parse it properly for a
real company name/description)? Recommendation: **lightweight, by
design, and deliberately**. Fetching and parsing every result's landing
page at discovery time would blur exactly the line the prior review's
Design Task 5 finding already protects — *"Discovery should discover,
Research should enrich"* — and would multiply per-result cost and
latency by however many results a job returns. A prospect with a
low-confidence, snippet-derived name and description is still a
perfectly valid `NEW`-status Prospect; if it survives dedup/scoring and
gets approved, that's exactly what M2/"M3" Research is for.

---

## 3. Provider Interface — review

**Confirmed: yes, Brave Search (and any future provider) can be added
without modifying the Discovery Engine itself.** The existing
`DiscoveryProvider` ABC (one `key`, one `search(query_spec, context) ->
ProviderSearchOutcome` method) already accommodates this — a
`BraveSearchProvider` is an import plus a registry entry, identical in
shape to how `ManualCSVProvider` plugs in today. Nothing about the
pipeline (`run_discovery_search()`), the dedup engine, or the scoring
engine needs to know Brave exists.

**Superseded by Section 11's Search Service refinement, in one
specific way:** the Discovery Engine itself will no longer hold a
direct reference to `get_provider(key)` for search-type providers at
all — it calls the Search Service, which owns the
`DiscoveryProvider`/registry relationship for search providers
internally. The ABC itself is unchanged; only *who calls it* changes.
See Section 11.1 for the full reasoning and the resulting dependency
direction.

**One real precondition, though, already flagged in the previous
review and worth restating as a hard dependency here:** the
"standard query-spec" shape (Section 2's Query-Spec Builder) needs to
exist *before* a second provider is added, or every provider ends up
inventing its own incompatible `query_spec` contract by convention
rather than by design — cheap to fix with one provider, expensive to
retrofit across three or four. This is why Section 10's phase plan
places it in Phase 1, ahead of Phase 2's first real provider.

No other interface changes are recommended. The ABC is intentionally
minimal, and that minimalism is exactly why it has already proven
reusable twice in this codebase (Delivery's provider family, now
Discovery's) — adding required fields to the interface itself (rather
than to the query-spec convention layered on top of it) would be the
wrong place to absorb Brave-specific or registry-specific needs.

---

## 4. Normalization Layer — review

**Agreed, and this closes a real gap.** A normalization layer does not
exist as its own pipeline stage today — what exists is `dedup.py`'s own
`normalize_website()`/`normalize_company_name()` functions, called
*inline, only at dedup time*, for dedup's purposes only (matching, not
producing a clean canonical candidate). There is no standalone,
independently-inspectable "this is the normalized version of this raw
candidate" object today.

**Worth noting explicitly: the schema already half-anticipated this.**
`DiscoveryProviderResult.normalized_payload` already exists as a column
— it's just not populated by a real, consistent normalization function
today. This is the natural home for the proposed stage, not a new
table.

**Recommendation:** promote normalization into its own explicit
pipeline stage, run on every `RawProviderResult` from every provider
(Brave's snippet-derived candidates need it more than a clean directory
row would, but the stage should be provider-agnostic), producing a
canonical shape: cleaned domain (existing `normalize_website` logic),
legal-suffix-stripped name (existing `normalize_company_name` logic),
resolved ISO country code (new — today country is a loose string),
and — tying back to the prior review's Design Task 6 gap — an attempt
at resolving free-text industry onto the `Industry` reference table via
deterministic keyword match. Persisted into the already-existing
`normalized_payload` column.

**Does this improve long-term scalability? Yes, concretely:**

1. **Single point of change.** A normalization rule fixed once applies
   to every provider automatically, instead of being reimplemented (or
   forgotten) inside each new provider.
2. **Downstream stages get simpler, not more complex.** Validation and
   dedup both currently have to defend against messy raw data
   themselves; if normalization guarantees a clean shape first, both
   stages shrink to their actual job (see Section 5's point about the
   CEO's own validation list conflating two concerns — normalization
   is exactly what disentangles them).
3. **Matches this project's own explainability discipline.** Every
   other stage in this pipeline (scoring's `score_breakdown`, dedup's
   `DuplicateMatch`) produces an inspectable, structured output, never
   a silent in-place mutation. Normalization should too.

---

## 5. Validation Layer — review

**Agreed it should be separate from deduplication — and the reason is
sharper than "these are just two different checks."** Deduplication
answers *"is this the same company as one we already have?"* Validation
answers a completely different question: *"is this even a real,
usable candidate at all, regardless of whether anything like it exists
already?"* Conflating them risks a bad candidate reaching dedup logic
that was never designed to also do quality gating.

**One correction to the CEO's own example list, flagged for
explicitly:** "Duplicate confidence" does not belong in Validation —
that's dedup's job by definition and already lives in `dedup.py`'s
`DuplicateMatch`. Keeping it there is the cleaner separation; listing it
under Validation would just recreate the conflation Validation is
supposed to fix. The rest of the CEO's list is a sound validation set:

- Valid domain syntax (cheap, no network call)
- Website reachable (an actual HTTP check — **note:** this is a
  per-candidate network call, and at scale needs its own rate limiting/
  parallelism budget, distinct from the provider's own API rate limit —
  flagged again in Section 9)
- Country recognized against a known ISO list (feeds directly off
  Normalization's resolved country code)
- Company name quality (not empty, not obviously search-engine
  boilerplate like "Home | Sitemap" — most relevant precisely because
  Brave's snippet-derived names are the weakest-quality names in the
  whole system, per Section 2)
- Required fields present (name + at least one of website/country)

**Should this become its own service? Yes.** Recommend
`app/discovery/validation.py`, run as its own pipeline stage between
Normalization and Deduplication, producing a structured verdict — pass/
fail plus per-check reasons, deliberately shaped like `score_breakdown`
and `DuplicateMatch` rather than a single boolean, so a failed
candidate is debuggable later rather than silently disappearing. A
candidate that fails validation should be recorded (on
`DiscoveryProviderResult`, which already exists precisely to hold every
raw hit regardless of outcome) rather than dropped — the difference
between "we found this but it didn't pass validation, here's why" and
"we never found this" matters for trusting the system at scale.

---

## 6. Multi-Provider Execution

### Today

Not yet relevant with one provider, but designed for now, ahead of
Phase 3, per the previous review's Design Task 9 finding: providers run
strictly sequentially inside one `for provider_key in
search.provider_keys` loop.

### Recommendation: hybrid, not purely parallel or purely sequential

**Across providers: parallel.** Provider calls are independent,
I/O-bound HTTP requests (Brave, OpenCorporates, or any future one) — no
reason one provider needs to finish before another starts. **Within one
provider: sequential, respecting that provider's own rate limit** (e.g.
Brave's 50 requests/second cap) — a provider shouldn't fan its own
pagination out faster than its own contract allows, independent of how
many *other* providers are running concurrently. This is genuinely
hybrid, not a compromise between two options — the two levels have
different constraints and should be governed independently.

### Cross-provider duplicate merging

The dedup engine itself doesn't need to change — `find_duplicate()`
already runs against every existing prospect regardless of which
provider produced it. The open question is **field-level merge
policy** when two providers both surface the same company with
different data (e.g. Brave's snippet-derived description vs.
OpenCorporates' registry-sourced legal name): recommend **prefer the
higher-confidence/more-structured source per field, never blanket
"last write wins."** Concretely: registry-sourced data (name, country,
registration number) should win over search-derived data for those
same fields, since Section 1 already established registries as the
more authoritative source for exactly that kind of fact; search-derived
description/keywords can still contribute where the registry has
nothing. Mechanically, this needs no schema change — `ProspectSource`
already models "this prospect was seen by these providers," so
attributing which field came from which source is additive, not a
redesign.

---

## 7. Rate Limiting & Failure Handling

**Recommendation: reuse the exact pattern already proven in this
codebase's Delivery domain, rather than inventing a new one.**
`app/delivery/dispatch_service.py`'s `_retry_or_fail` already
distinguishes **transient** failures (timeout, 429 rate-limited, 5xx —
worth a bounded retry with backoff) from **permanent** failures (403,
malformed query, invalid API key — retrying is pointless, log and move
on), each with an explicit `permanent: bool` flag on the failure
record. A `BraveSearchProvider` (or any future provider) should use the
identical vocabulary and the identical decision structure — not because
it's convenient, but because it means one mental model covers failure
handling across the whole platform, not two.

**Job continuation:** already correctly isolated today —
`DiscoveryJobProviderRun` tracks per-provider status independently, so
one provider's exhaustion or persistent failure already cannot fail the
whole job. This property needs to be preserved, not rebuilt, as real
providers are added.

**Provider health:** recommend a lightweight consecutive-failure
counter per provider (mirroring the previous review's Section 3
suggestion of a Delivery-style `ProviderConnection.status` concept) —
after N consecutive failures within a job, or across jobs, stop
attempting that provider automatically and surface it as needing
attention, rather than every subsequent job wasting a call finding out
the same provider is still down.

---

## 8. Legal & Compliance — direct assessment per provider

- **Google Custom Search:** legally fine while it lasts, but "while it
  lasts" is the whole problem — closed to new signups, hard retirement
  January 1, 2027. Not a compliance risk; a planning risk.
- **Bing Search API:** moot — retired August 2025, cannot be built on
  at all.
- **Brave Search API:** lowest-risk of the search-engine options.
  Official, published commercial ToS, SOC 2 Type II, GDPR-compliant.
  Two concrete obligations to design in from day one rather than
  retrofit: (1) do not use returned results to train/fine-tune/
  benchmark any AI model — irrelevant to M2's use (extracting company
  candidates, not model training) but worth stating explicitly so a
  future AI-reasoning milestone (the previous review's Design Task 7
  follow-on) doesn't accidentally cross this line by training on stored
  Brave result data; (2) "Powered by Brave" attribution must appear
  wherever the underlying search results are shown to a user — a small,
  concrete UI requirement for whatever surface eventually shows raw
  candidate sourcing.
- **Europages / Kompass:** **highest risk of every option reviewed.**
  Neither has a public official API; every integration path found is a
  third-party scraper. Two distinct exposures: contractual (violating
  the directory's own terms) and, specific to the EU, sui generis
  database-right protection over directory compilations — a real,
  distinct legal regime from copyright that specifically covers exactly
  this kind of structured-listing scraping. Recommend not pursuing
  either without a licensed commercial data relationship first.
- **Government registries (OpenCorporates / national registries
  directly):** **cleanest footing of any option.** Public-record data,
  explicit commercial API terms, straightforward pricing. Recommended
  as both a future provider and, sooner, a Validation-layer data source.
- **Trade fair exhibitor lists / other structured sources:** no
  consistent legal profile across organizers — case-by-case, not a
  general recommendation either way at this stage.

---

## 9. Scalability — challenging the plan's own framing

The previous review already flagged that today's sequential-provider,
full-in-memory-dedup design would struggle at 10,000–100,000 results.
Adding a real search-engine provider surfaces a **second, different**
scale problem worth naming explicitly, because it's not an
infrastructure problem — it's a query-strategy problem:

**Search APIs cap how many results a single query can return.**
Most general search engines, Brave included, only return a bounded
number of result pages per query before results stop being meaningfully
distinct or the API stops paginating further. This means **a 100,000-
candidate job cannot be "one query, paged deeply"** — it structurally
requires **many distinct query variations** (different keyword phrasing,
different city/region combinations within the target country, different
buyer-type synonyms) fanned out and merged, each contributing a modest
number of results. This is precisely why Section 2's Query-Spec Builder
was specified as producing a **set** of queries, not one — that design
choice isn't stylistic, it's the actual mechanism that makes
large-scale jobs possible at all with a search-engine-style provider.

Concretely, by scale:

- **100 companies:** trivial. A handful of query variations against
  Brave, no infrastructure concerns at all.
- **1,000 companies:** still comfortable, but this is roughly where
  Validation's per-candidate reachability check (Section 5) starts to
  matter as its own rate-limited concern, separate from the provider's
  own API rate limit.
- **10,000 companies:** query-variation fan-out becomes a real
  requirement, not an optimization — a single query's result ceiling
  won't get there. This is also where the prior review's in-memory
  dedup-scan concern starts to bite in practice, independent of the
  provider question.
- **100,000 companies:** both problems compound. This scale needs
  query-variation fan-out, parallel provider execution across those
  variations (Section 6), indexed (not full-memory-scan) dedup, and
  almost certainly needs to be reframed as **several smaller jobs
  covering narrower query slices** rather than one monolithic
  `DiscoveryJob` — worth an explicit product decision (does the UI
  present this as one job or a batch of related jobs?) before it's
  built, not discovered as a limitation after.

**The challenge to surface directly:** treating scale purely as "make
the execution engine parallel/indexed enough" (this document's Section
6, and the previous review's Section 9) is necessary but not
sufficient for a search-engine-based provider specifically — the query
strategy itself has to be scale-aware, or the fastest, best-indexed
execution engine in the world still can't overcome a provider that
structurally cannot return more than a few hundred results per query.

---

## 10. Recommended Implementation Order — reviewing the CEO's plan

The proposed seven-phase order is broadly sound, and Phase 1's instinct
(strengthen the existing core before adding a real provider) is
correct — building a real, costed, rate-limited provider integration on
top of unvalidated, unnormalized, hardcoded-weight scoring would mean
debugging two kinds of new problems at once instead of one. Two
specific issues worth flagging before treating the plan as final,
though — not disagreements with the direction, but redundancies and one
resequencing that would make the plan tighter:

1. **Phases 4 and 5, as listed, largely already exist.** "AI Research"
   (Phase 4) is already a separate, working milestone with its own
   context/pipeline (previous review, Design Task 5) — it doesn't
   depend on anything in M2's provider work and isn't gated behind it;
   listing it as an M2 phase risks someone rebuilding something that
   already works. Likewise "ICP Matching & Explainable Scoring"
   (Phase 5) already exists as a four-factor deterministic engine with
   full `score_breakdown` explainability (previous review, Design Tasks
   6–7) — what's actually missing (the industry factor, configurable
   weights) is *already listed* under the CEO's own Phase 1
   ("configurable scoring"). **Recommend dropping Phase 4 and Phase 5 as
   separate phases** — fold the genuine industry/configurable-weight
   gap into Phase 1, and treat Research as already done, not a phase of
   this milestone.
2. **"Prospect Import" appears in both Phase 1 and Phase 6.**
   Recommend keeping it in one place only — Phase 1, since it's pure
   internal strengthening with no dependency on any external provider,
   and delivers value (a working end-to-end path from an already-
   existing manually-imported prospect to a real Opportunity) even
   before a single automated provider exists.
3. **Phase 1 as written bundles six genuinely separable pieces of work**
   (normalization, validation, dedup signal expansion, configurable/
   industry scoring, prospect import, job cancellation) into one phase.
   Recommend keeping "Phase 1" as the CEO's umbrella label but running
   it as explicit sub-phases (1a normalization + validation; 1b dedup
   signal expansion + configurable scoring; 1c prospect import + job
   cancellation), each independently proposed/approved/verified — this
   matches this project's own standing discipline (small, reviewable
   units of work) better than one large combined change.

### Consolidated recommendation (superseded by Section 11 — see updated table there)

The table originally here is superseded by Section 11.3's updated
phase table, which folds in the Search Service and Query Planner. Kept
below, struck through in spirit, purely so the reasoning trail (why
Phases 4/5 were dropped, why Prospect Import was deduplicated) remains
visible in one place:

| Phase (original) | Scope |
|---|---|
| **1** | Core strengthening, sub-phased: (1a) Normalization + Validation layers; (1b) dedup signal expansion (VAT/registration number) + industry scoring factor + configurable weights; (1c) Prospect Import action + job cancellation. No external provider dependency — all of this can be built and verified against the existing `ManualCSVProvider` data. |
| **2** | First automated provider: **Brave Search API**, including the Query-Spec Builder and the lightweight Candidate Extraction step (Section 2). |
| **3** | Second provider — **OpenCorporates** (both as a genuine second discovery source and as the Validation layer's registry-verification data source) — plus true parallel multi-provider execution and the cross-provider field-merge policy (Section 6). |
| **4** | Scale hardening: query-variation fan-out strategy for large jobs (Section 9), indexed dedup, parallel/chunked execution. Deferred until Phase 2/3 provide real volume to profile against, per the previous review's own reasoning. |

Research and Explainable Scoring are intentionally absent as separate
phases — the first already exists and runs independently of M2; the
second already exists and its one real gap is folded into Phase 1.

---

## 11. Approved Refinements — Search Service Abstraction & Query Planner

**Status: CEO-approved, incorporated into the architecture below.
Both refinements were approved together with the rest of this
document; Sections 2 and 3 above have been updated with pointers into
this section. This section is the authoritative description of both —
where anything above conflicts, this section wins.**

### 11.1 Search Service abstraction

**Directive:** the Discovery Engine must never directly depend on
Brave or any other search provider. The dependency chain becomes:

```
Discovery Engine
      │
      ▼
Search Service
      │
      ▼
Brave  │  Future Search Providers  │  Enterprise Search  │  ...
```

**Why this is the right refinement, not just an extra layer for its
own sake:** the original design (Section 3) already had the Discovery
Engine calling `get_provider(key)` and invoking `.search()` directly —
architecturally fine for *one* provider, but it means the Discovery
Engine's own code would need to know how to fan a query out across
multiple search providers, merge their results, and apply
provider-specific concerns (Brave's rate limit, a future Enterprise
Search connector's auth model) — none of which is actually Discovery's
job. The Search Service isolates all of that behind one interface, so
adding "Enterprise Search" (an internal company directory, a customer's
own CRM export, or any future source Discovery itself shouldn't need to
understand) later touches only the Search Service, never
`pipeline.py`.

**Where this sits relative to the existing `DiscoveryProvider` ABC:**
the ABC is not replaced — it's relocated conceptually. The Search
Service becomes the sole owner of the `PROVIDER_REGISTRY`/
`get_provider()` relationship for search-type providers; it is the only
component that imports `BraveSearchProvider` or any future search
provider directly. The Discovery Engine's `pipeline.py` calls exactly
one method on the Search Service (e.g. `search_service.discover(query_plan,
context) -> list[RawProviderResult]`) and never imports a provider
module at all.

**Proposed interface (design only, not yet built):**

```python
class SearchService:
    def discover(
        self, query_plan: QueryPlan, context: DiscoveryContext
    ) -> list[RawProviderResult]:
        """Executes every query variation in query_plan against every
        enabled search provider, merges results, and returns the
        unified candidate list. Callers (the Discovery Engine) never
        see individual provider calls, retries, or rate limits."""
```

Internally, `SearchService.discover()` is where Section 6's
"parallel-across-providers, sequential-within-one-provider's-own-rate-
limit" execution model lives, and where Section 7's
transient/permanent retry handling and per-provider health tracking
live. None of that logic belongs in `pipeline.py` — this is the
concrete mechanism that keeps it out.

**Manual/CSV discovery is unaffected.** `ManualCSVProvider` is not a
*search* provider — it never executes a query, a human pastes rows
directly. It stays exactly where it is today, called directly by the
Discovery Engine via the existing `DiscoveryProvider` ABC, outside the
Search Service entirely. The Search Service is specifically the
abstraction for query-driven providers (Brave today; OpenCorporates,
Europages-via-license, Enterprise Search, or anything else later).

### 11.2 Query Planner

**Directive:** rather than the Discovery Engine (or, as originally
proposed in Section 2, a "Query-Spec Builder Service" sitting inside
Discovery) constructing a single query, a dedicated Query Planner
generates multiple query variations from: Products, ICP, Buyer Types,
Industries, Countries, Languages, and Synonyms. The Search Service
executes the resulting set and merges results before anything reaches
Normalization.

**This directly confirms and formalizes Section 9's own finding** —
that a 100,000-candidate job cannot be one query paged deeply, and
structurally requires many query variations fanned out and merged.
The Query Planner is the component that makes that mechanism real
rather than aspirational.

**Proposed responsibilities (design only):**

- Takes the same inputs the original Query-Spec Builder was scoped to
  read (Company Profile, Products, ICP Criteria: target buyer types,
  target markets/countries, and — once Phase 1b lands —
  target industries), plus two inputs the CEO's refinement adds
  explicitly beyond the original proposal: **Languages** (query
  variations in the target country's language(s), not just English —
  ICPCriteria already has a `languages` relationship today, previously
  unused for this purpose) and **Synonyms** (buyer-type/industry
  terminology variation — e.g. "importer" / "wholesaler" / "distributor"
  for the same underlying buyer type, "textile" / "fabric" / "apparel
  materials" for the same industry).
- Produces a `QueryPlan` — an explicit, inspectable list of concrete
  query strings (not a single opaque `query_spec` dict as originally
  sketched), each tagged with which factor(s) produced it (e.g.
  `{"query": "Textilimporteur Deutschland", "language": "de",
  "buyer_type_synonym": "importer", "country": "DE"}`). Making this
  explainable, not just functional, matters here for the same reason
  Section 7/8 of the previous review insisted scoring stay explainable
  — a CEO or user reviewing why a job returned what it did should be
  able to see which query produced which candidate, not just a final
  merged list.
- Is called once by the Search Service at the start of
  `discover()`, not by the Discovery Engine — keeping with 11.1's
  dependency direction, the Discovery Engine never constructs a query
  itself.

**Where does Candidate Extraction (Section 2's step turning a web
result into a company) live?** Inside the Search Service, immediately
after a provider's raw results come back and before they're returned to
the Discovery Engine — it's a provider-response concern (turning
Brave's page-shaped results into company-shaped ones), not a Discovery
Engine concern, and not a Query Planner concern (which only builds
queries, never interprets results). This keeps each component's
responsibility to exactly one verb: Query Planner *plans*, Search
Service *executes and extracts*, Discovery Engine *normalizes,
validates, deduplicates, and scores*.

### 11.3 Updated flow (supersedes Section 2's diagram)

```
Workspace → Company Profile + Products + ICP Criteria (+ Languages, Synonyms)
      │
      ▼
Query Planner  →  QueryPlan (explicit, explainable list of query variations)
      │
      ▼
Search Service  →  for each enabled search provider (parallel across
      │             providers, sequential within each provider's own
      │             rate limit): execute QueryPlan's variations,
      │             Candidate Extraction, merge results
      ▼
RawProviderResult (unified, as already designed) — this is the
      │             boundary the Discovery Engine actually sees
      ▼
Normalization → Validation → Deduplication → Scoring → Prospect
      (all existing/proposed Discovery Engine internals, unchanged)
```

### 11.4 Updated consolidated phase table

| Phase | Scope |
|---|---|
| **1** | Core strengthening, sub-phased: (1a) Normalization + Validation layers; (1b) dedup signal expansion (VAT/registration number) + industry scoring factor + configurable weights; (1c) Prospect Import action + job cancellation. No external provider or Search Service dependency — built and verified against existing `ManualCSVProvider` data. |
| **2** | **Search abstraction + Brave Search**: build the Search Service (11.1) and Query Planner (11.2) together with the first real provider, `BraveSearchProvider`, wired in behind them — the abstraction and its first real consumer land in the same phase so the interface is proven against a real provider immediately, not designed speculatively ahead of any concrete need. |
| **3** | **OpenCorporates + multi-provider execution**: second provider registered with the Search Service, real parallel-across-providers execution (11.1), cross-provider field-merge policy (Section 6). |
| **4** | **Scale hardening**: query-variation fan-out at real volume (Section 9), indexed dedup, parallel/chunked execution — profiled against Phase 2/3's real traffic. |

This matches the CEO's own approved order exactly (Phase 1 → Phase 2
"Search abstraction + Brave Search" → Phase 3 → Phase 4); the only
change from Section 10's original table is folding 11.1/11.2 explicitly
into Phase 2's scope, since neither refinement is separable from "build
the first real provider" — a Search Service with nothing behind it, or
a Query Planner with no Search Service to hand its plan to, would be
unvalidated design in isolation.

---

## Summary

**Approved.** Recommended first provider: **Brave Search API** — the
only actively maintained, officially licensed, general-purpose search
API left after Bing's August 2025 retirement and Google's confirmed
January 2027 sunset, and the only source type here that can answer an
open-ended semantic query the way the platform's own founding example
requires. Recommended second provider: **OpenCorporates**, for the
opposite reason — authoritative registry data for validation and the
strongest possible dedup signal, not open-ended discovery.

Normalization and Validation become their own explicit pipeline
stages (not folded into dedup), reusing schema that already exists
(`normalized_payload`) rather than requiring new tables. A Search
Service now sits between the Discovery Engine and every search
provider (11.1), and a Query Planner generates and explains multiple
query variations from Products/ICP/Buyer Types/Industries/Countries/
Languages/Synonyms, executed and merged by the Search Service before
Normalization (11.2). Multi-provider execution is parallel across
providers, sequential within one provider's own rate limit. Failure
handling reuses the transient/permanent distinction already proven in
the Delivery domain. Europages and Kompass are not recommended without
a licensed data relationship, given the absence of any official API.
Scale at the 100,000 tier requires a query-variation strategy, not just
a faster execution engine.

Implementation proceeds per Section 11.4's phase table, starting with
Phase 1a (Normalization + Validation layers). Each phase/sub-phase
follows this project's normal proposal → approval → implementation →
verification cycle; this document constitutes approval of the overall
plan, not a blanket pre-approval of every implementation detail within
it.

---

## Sources

- [Bing Search APIs Retirement — Microsoft Lifecycle](https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement)
- [Bing Search APIs Retiring August 11, 2025 — Search Engine Roundtable](https://www.seroundtable.com/bing-search-apis-retiring-august-11-2025-39406.html)
- [Microsoft ends Bing Search APIs, alternative costs 40–483% more — PPC Land](https://ppc.land/microsoft-ends-bing-search-apis-on-august-11-alternative-costs-40-483-more/)
- [Google Custom Search JSON API Pricing — expertrec.com](https://blog.expertrec.com/google-custom-search-json-api-simplified/)
- [Custom Search JSON API — Google for Developers](https://developers.google.com/custom-search/v1/overview)
- [Brave Search API Terms of Service](https://api-dashboard.search.brave.com/documentation/resources/terms-of-service)
- [Brave Search API Pricing 2026 — TrustRadius](https://www.trustradius.com/products/brave-search-api/pricing)
- [Brave Search API Pricing — costbench.com](https://costbench.com/software/ai-search-apis/brave-search-api/)
- [OpenCorporates — Pricing, Reviews, Data & APIs — Datarade](https://datarade.ai/data-providers/opencorporates/profile)
- [OpenCorporates Enterprise API Terms of Service](https://opencorporates.com/legal-information/enterprise-api-terms-of-service/)
- [Getting started with the OpenCorporates API](https://blog.opencorporates.com/2025/02/13/getting-started-with-the-opencorporates-api/)
- [Europages Scraper — Apify](https://apify.com/santamaria-automations/europages-scraper/api)
- [Kompass Scraper — Apify](https://apify.com/santamaria-automations/kompass-scraper/api/openapi)
