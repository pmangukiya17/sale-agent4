# M2 Phase 1b — Dedup Signal Expansion + Configurable/Industry Scoring

**Status: architecture proposal only. No implementation. Builds on the
approved Phase 1a (`app/discovery/normalization.py`,
`app/discovery/validation.py`) and the two prior architecture reviews
(`m2-buyer-discovery-engine-architecture-review.md`,
`m2-discovery-provider-strategy.md`). Every claim below about current
code was re-verified against the real files in this pass, not assumed
from memory of the earlier reviews.**

---

## 1. Objectives

Close the two gaps the original architecture review identified as
Phase 1b's scope, and no more than that:

1. **Dedup signal expansion** — today's dedup engine (`app/discovery/
   dedup.py`) only ever checks website-exact-match and fuzzy-name+
   country. Add VAT number, registration number, and (with a
   reconsideration flagged in Section 7) email as additional signals,
   with an explicit conflict-resolution order.
2. **Configurable, industry-aware scoring** — today's scoring engine
   (`app/discovery/scoring.py`) has four factors with hardcoded module-
   level weights and no Industry factor at all, despite `Industry` and
   `Prospect.industry_id` already existing (and, since Phase 1a, now
   actually being populated). Add a fifth Industry Match factor and
   make per-factor weights configurable per ICP.

Explicitly **out of scope** for this sub-phase, same as Phase 1a: no
new search providers, no Search Service/Query Planner (both Phase 2),
no schema-breaking changes to `DiscoveryJob`/`DiscoveryRun`, no worker
or event changes. Everything here is testable against the existing
`ManualCSVProvider` and the existing async pipeline, exactly like
Phase 1a was.

---

## 2. Current architecture analysis

**Deduplication (`app/discovery/dedup.py`, post-Phase-1a):** two tiers.
Definite match on `normalize_website()`-equal domains (confidence 1.0,
auto-merge). Otherwise fuzzy match on `normalize_company_name()` +
exact country string equality, via `difflib.SequenceMatcher`, banded at
`DEFINITE_MATCH_THRESHOLD = 0.85` / `POTENTIAL_MATCH_THRESHOLD = 0.6`.
Called from `pipeline.py`'s per-candidate loop against `existing_
prospects`, a full in-memory list scoped to one `company_profile_id`
(Section 9's scalability note revisits this). As of Phase 1a, the
`Prospect` import here is behind `TYPE_CHECKING` (zero-dependency,
reusable by `normalization.py`) — this pattern should be preserved by
whatever Phase 1b adds.

**Scoring (`app/discovery/scoring.py`):** four factors, each an
independent function returning `{factor, weight, matched, points,
explanation}`: `_score_buyer_type` (weight 25), `_score_market` (25,
with a force-disqualifying excluded-market check), `_score_company_size`
(20), `_score_product_relevance` (30, keyword overlap between `Product.
keywords`/`applications` and `Prospect.description`). Weights are
module-level constants (`WEIGHT_BUYER_TYPE` etc.), summing to 100,
**never read from `ICPCriteria` at all** — `ICPCriteria.weight` (a
single float column, default 1.0) exists but is unused by `scoring.py`.

**`ICPCriteria` (`app/models/icp_criteria.py`), the model that will
carry most of this phase's new configuration:** already has four
many-to-many relationships via dedicated junction tables in `app/
models/associations.py` (`target_buyer_types`, `target_markets`,
`excluded_countries`, `languages`) — **no `target_industries`
relationship exists**, even though `Industry` (`app/models/industry.py`)
and `CompanyProfile.industries` already exist elsewhere. Critically,
`ICPCriteria` already has a `rules: Mapped[dict] = mapped_column(JSONB,
...)` column, whose own docstring calls it *"escape hatch for free-form
criteria that don't have a modeled column yet"* — this is the natural,
already-existing home for configurable weights (Section 8).

**`Prospect` (`app/models/prospect.py`):** has `industry_id` (FK to
`Industry`, nullable, existed since M1, now actually populated by
Phase 1a's normalization stage) and `industry_raw`. Has **no
`vat_number`, `registration_number`, or company-level `email` field**.
The only `email` field anywhere on the discovery side is `ProspectContact.
email` — a per-*person* field, not a per-*company* one.

**`ManualCSVProvider` / `RawProviderResult`:** `RawProviderResult`
(`app/discovery/providers/base.py`) has no VAT/registration/email
fields either. `ManualCSVProvider.search()` (`app/discovery/providers/
manual_csv.py`) reads each row generically via `row.get(...)` — adding
new optional fields here is a one-line-per-field change, not a
redesign. The frontend's row-entry form (`CandidateBuyerRow` in
`DiscoverySearches.tsx`) similarly has no fields for these today.

---

## 3. Integration with the existing Discovery pipeline

No change to `pipeline.py`'s control flow or call sites. Both pieces of
this phase slot into functions the pipeline already calls:

- Dedup expansion lives inside `dedup.py`, called from the same
  per-candidate loop in `pipeline.py` that Phase 1a already modified to
  pass *normalized* (not raw) `name`/`website`/`country`. The new
  identifier-based tier reads normalized `vat_number`/`registration_
  number` the same way.
- Scoring expansion lives inside `scoring.py`, called from `pipeline.
  py`'s `_score_and_apply()`. No signature change to `score_prospect()`
  beyond it now also reading `icp.target_industries` and (optionally)
  `icp.rules.get("scoring_weights")`.

**One real gap worth deciding explicitly, not assuming:** `ManualCSV
Provider` is the *only* registered provider until Phase 2, and its row
schema (and the frontend form that feeds it) has no VAT/registration
fields today. Without extending both, **the new dedup tier would have
no way to be exercised end-to-end with real data before Phase 2 ships**
— it would only ever be reachable via unit tests with synthetic
`RawProviderResult` objects. Recommended (see Section 12's consolidated
list): extend `RawProviderResult`, `ManualCSVProvider`'s row reading,
and the frontend's `CandidateBuyerRow` form with the same two optional
fields, so this phase is genuinely end-to-end testable, not just
unit-testable. This is a small, additive change, not a redesign of
either.

---

## 4. Database changes

One new Alembic migration (`0027_...`, migration head is currently
`0026_mailbox_brief`, confirmed unchanged since Phase 1a):

- **`prospects` table:** add `vat_number: str | None`, `registration_
  number: str | None`, `email: str | None` — all nullable `String`
  columns, no default. Add a plain (non-unique — see Section 7 on why
  not unique) index on each of `vat_number` and `registration_number`
  to support the indexed exact-match lookup proposed in Section 10;
  `email` does not need an index under the recommendation in Section 7
  (not used as a dedup key).
- **`icp_criteria_target_industries` junction table** — identical shape
  to the four existing junction tables in `associations.py`: composite
  primary key on `(icp_criteria_id, industry_id)`, both `ON DELETE
  CASCADE`, no extra columns. `ICPCriteria` gains a `target_industries:
  Mapped[list["Industry"]]` relationship via this table, following the
  exact same pattern as `target_buyer_types`.
- **Configurable weights: no new column.** `ICPCriteria.rules` (JSONB,
  already exists) gains one new, API-validated key,
  `rules["scoring_weights"]`, a `dict[str, float]` keyed by factor name
  (`buyer_type_match`, `market_match`, `company_size_match`,
  `product_keyword_relevance`, `industry_match`). This is exactly what
  the `rules` column's own docstring describes it for.

**No schema change for the normalized-form storage of VAT/registration
numbers.** Matching the existing precedent (`Prospect.website` stores
the raw provider value; `normalize_website()` computes a comparison
form transiently inside `dedup.py`, never persisted as a second
column), `vat_number`/`registration_number` should store the raw value
as typed, with a new `normalize_vat_number()`/`normalize_registration_
number()` pair in `normalization.py` computing the comparison form
on-the-fly wherever needed (dedup, and the new indexed lookup in
Section 10). No `normalized_vat_number` column.

---

## 5. API changes

- `ICPCriteriaCreate`/`ICPCriteriaUpdate` gain an optional `target_
  industry_ids: list[UUID]`, mirroring the existing `target_buyer_type_
  ids`/`target_market_ids` pattern already used for the other junction
  tables. `ICPCriteriaRead` gains `target_industries: list[IndustryRead]`.
- `ICPCriteriaCreate`/`ICPCriteriaUpdate` gain an optional `scoring_
  weights: dict[str, float] | None`, validated at the API layer (not
  deep inside `scoring.py`) against exactly the five known factor
  names, and — per the recommendation in Section 8 — rejected with a
  400 if the provided weights don't sum to 100. Stored into `rules[
  "scoring_weights"]` on write; this is a schema-level convenience so a
  caller doesn't need to know about the generic `rules` escape hatch
  directly. `ICPCriteriaRead` exposes `scoring_weights` the same way
  (read back out of `rules`, defaulting to the module-level defaults
  when absent, so a client always sees a complete five-key dict, not a
  possibly-partial one).
- `ProspectRead` gains `vat_number`, `registration_number`, `email` as
  plain read-only fields — no new route, since Prospects are only ever
  created by the pipeline itself, never via a public POST.
- If the manual-provider extension from Section 3 is adopted:
  `DiscoverySearchUpdate`'s existing free-form `query_spec` needs no
  schema change (it's already an untyped `dict[str, Any]`) — only
  `ManualCSVProvider.search()`'s row-reading and the frontend's
  `CandidateBuyerRow` interface need the two new optional fields.
- **No changes to `/run`, `/discovery-jobs`, or any Workflow-Engine-
  facing route.** This phase is a data/scoring enrichment, not an
  execution-model change.

---

## 6. Worker/event changes

**None.** `DiscoveryExecutionAction`, the Event Dispatcher, and the Step
Runner are untouched — every change in this phase lives inside pure
functions (`dedup.py`, `scoring.py`) or schema-validation code already
called by the existing, unchanged pipeline. No new event type, no new
`WorkflowDefinition`, no new worker process. Identical claim, and
identical reasoning, to Phase 1a's.

---

## 7. Deduplication strategy

### Proposed three-tier order (most authoritative first)

1. **Government identifier match (NEW) — VAT number or registration
   number, either one matching is sufficient.** Confidence 1.0,
   auto-merge, same behavior as today's website tier. Compared via new
   `normalize_vat_number()`/`normalize_registration_number()` functions
   (strip whitespace/punctuation, uppercase, matching the existing
   `normalize_website()` pattern) — never raw string equality.
   **Re-ordered ahead of website matching**, not alongside it: a real
   company can change its domain (rebrand, migrate providers) far more
   plausibly than its government registration ever changes, so this is
   the single strongest available signal and should short-circuit
   first.
2. **Website exact match (existing, unchanged).** Confidence 1.0,
   auto-merge.
3. **Fuzzy name + country match (existing, unchanged).** `DEFINITE_
   MATCH_THRESHOLD`/`POTENTIAL_MATCH_THRESHOLD`, human review in the
   ambiguous band.

### Email — reconsideration, not a silent decision

The CEO's brief lists email among the dedup signals to add. Flagging
this rather than deciding it silently: **a company-level email is a
structurally weaker signal than VAT/registration/website.** VAT and
registration numbers are (by design, government-issued) unique per
legal entity; a website is normally one canonical domain per real
company. An email address has no equivalent uniqueness guarantee — a
franchise network, reseller group, or holding company can legitimately
route many distinct legal entities through one shared `info@`/`sales@`
inbox, and this project's own schema already treats email as a
*person*-level fact (`ProspectContact.email`), not a company-level one.

**Recommendation: do not add email as a company-level Prospect dedup
key in this phase.** If a company-level email genuinely needs to be
captured (e.g. a general inquiries address a provider surfaces), store
it on `Prospect.email` as data (Section 4 already proposes the column)
but exclude it from `find_duplicate()`'s matching logic entirely —
email-based matching, if ever wanted, belongs at the `ProspectContact`
level as a separate, smaller, future concern with its own review, not
folded into company-level dedup here.

### Conflict handling

If two providers disagree on a prospect's VAT/registration number (one
says X, a later one says Y for what looks like the same company by
website/name), **do not auto-resolve.** Flag `DUPLICATE_REVIEW` for a
human, the same discipline `dedup.py` already applies to the ambiguous
fuzzy-name band — a wrong auto-merge on conflicting government
identifiers is a worse failure than asking a human once. Record which
tier/signal produced any match on `ProspectSource`/`ProspectTimelineEvent`
(both already carry arbitrary JSON payloads) so every merge stays
explainable, consistent with this project's existing discipline.

### Validation ordering

A malformed VAT/registration number should never reach the dedup tier
at all. Recommend adding structural format checks (not full per-country
regex validation — out of scope here — but basic shape checks: non-
empty, reasonable length/charset) to `app/discovery/validation.py`
(Phase 1a's module — this is exactly the kind of "is this well-formed"
check that module already owns), so a garbage value fails Validation
and never gets a chance to cause a false-positive exact-match merge.

---

## 8. Configurable scoring architecture

### New factor: `_score_industry()`

Mirrors `_score_buyer_type()`'s exact shape: reads `icp.target_
industries`, "no preference" fallback (full credit) if the ICP
specifies none, matched via `prospect.industry_id` (populated by
Phase 1a) against the target set. Same `{factor, weight, matched,
points, explanation}` output shape as every other factor — zero change
to the explainability contract.

### Rebalancing weights — an open question, not a silent choice

Adding a fifth factor requires new weights summing to 100. **This
document does not pick the final numbers** — that's a product decision
the CEO should make explicitly, since it changes every future Prospect's
effective scoring emphasis. One illustrative option, offered only as a
starting point for discussion:

| Factor | Current | Illustrative 5-factor split |
|---|---|---|
| Buyer Type Match | 25 | 20 |
| Market Match | 25 | 20 |
| Company Size Match | 20 | 15 |
| Product Keyword Relevance | 30 | 25 |
| Industry Match (new) | — | 20 |

### Per-ICP configurability

`score_prospect()` reads `icp.rules.get("scoring_weights", {})`, using
the module-level default for any factor key not present (so an ICP
overriding only one weight doesn't have to specify all five). This
keeps `scoring.py`'s function itself simple: it trusts its input is
already valid, because validation happens once, at the API layer
(Section 5), not on every scoring call.

**Recommendation, stated explicitly for reconsideration:** enforce
`sum(scoring_weights.values()) == 100` at write time (API-layer 400 on
violation) rather than either (a) silently rescaling at score time,
which changes the "out of 100" meaning listeners already assume, or
(b) allowing an arbitrary sum, which would break `_score_and_apply()`'s
existing `(total_score / 100.0) >= icp.minimum_confidence_score` math.
Failing loud at configuration time, rather than producing a
quietly-miscalibrated score later, matches this project's existing
`DiscoveryConfigError`/`ProviderError` discipline.

---

## 9. Multi-business implications

Every piece of this phase is already scoped correctly for multi-tenancy
by construction, not by any new code this phase needs to write:
`ICPCriteria` (and therefore `target_industries` and `rules.scoring_
weights`) is already keyed by `company_profile_id`, so per-business
custom industries/weights are automatically isolated. `vat_number`/
`registration_number`/`email` live on `Prospect`, likewise already
scoped.

**One limitation worth stating explicitly, not discovering later:**
`find_duplicate()` (and its proposed new identifier-based sibling, see
Section 10) only ever compares within one business's own
`existing_prospects` — the new VAT/registration tier must preserve this
scoping exactly. Two different businesses on this platform independently
discovering the same real-world company (same real VAT number) will
each get their own, separate `Prospect` row — this is a deliberate,
documented limitation, not a bug. Cross-tenant identity resolution is a
materially larger feature with its own data-sharing/consent questions
and is explicitly not part of this phase.

---

## 10. Scalability considerations

The new government-identifier tier is an **exact match**, which — unlike
the existing fuzzy-name tier — can be made genuinely indexed rather
than requiring the full in-memory `existing_prospects` scan the current
`find_duplicate()` already does. Recommend: a new, separate function
(not folded into the existing pure `find_duplicate()`), e.g. `find_
duplicate_by_identifier(db, company_profile_id, vat_number,
registration_number) -> Prospect | None`, issuing one indexed `SELECT
... WHERE company_profile_id = ... AND (vat_number = ... OR
registration_number = ...)` query, checked *before* falling back to the
existing pure, DB-free `find_duplicate()` for the website/fuzzy-name
tiers.

**This is a real design decision to make explicitly:** today's `dedup.
py` is 100% pure Python, no DB access, which is exactly what makes its
functions independently unit-testable (as `tests.test_discovery_
dedup_pure` already demonstrates). Adding one DB-touching function
alongside it is a deviation from that purity, but a narrow, justified
one — recommend keeping it in a *new* function rather than changing
`find_duplicate()`'s own signature, preserving today's test story for
the tiers that don't need indexing while getting a real, incremental
step toward the scalability problem the original review's Section 9
already flagged (full in-memory dedup scan) — without waiting for the
full Phase 4 rewrite.

Scoring's per-factor cost is unaffected by any of this — one more O(1)
factor, no scalability concern regardless of job size.

---

## 11. Future compatibility with M3–M7

No change to the Workflow Engine Event/Action boundary the previous
reviews already praised. Research (M2/"M3" in old numbering) reads
whatever's on `Prospect` at trigger time — it will automatically see
`industry_id`, `vat_number`, `registration_number`, `email` the moment
they're populated, with zero additional wiring. The richer, five-factor
`score_breakdown` and any per-ICP custom weights flow through the exact
same JSONB shape every downstream consumer (Personalization, Outreach,
Reply Intelligence, the Command Center's Executive Daily Brief) already
reads generically — nothing downstream needs to change to benefit.

One forward-looking note, not a Phase 1b requirement: a future AI-
narrative pass over `score_breakdown` (the previous review's Design
Task 7 follow-on) should also read `icp.rules.scoring_weights` when
present, so a generated narrative correctly says "your ICP weighted
Market Match higher than the default" rather than assuming everyone
uses the default split. Worth writing down now so that future
milestone doesn't have to rediscover it.

---

## 12. Risks and trade-offs

- **Retroactive weight/factor changes don't get retroactively applied.**
  Deploying new default weights (or the new Industry factor) changes
  what a *future* scoring pass produces; it must not silently rewrite
  already-recorded `score_breakdown` history — matches this project's
  "frozen, permanent record" ethos already established for
  `DiscoveryRun`. Recommendation: leave historical scores exactly as
  recorded; only the next scoring pass (re-run, re-discovery, or an
  explicit future rescore action) uses the new weights/factor. A
  consequence worth flagging: two prospects scored under different
  weight regimes aren't directly comparable by number alone without a
  UI surfacing which weight-set produced each — no schema change
  needed (`ProspectTimelineEvent`'s existing `score_updated` payload
  already timestamps each scoring pass), just a future UI note.
- **False-positive risk on the new identifier tier.** A mistyped or
  reused government ID could cause an incorrect confidence-1.0 auto-
  merge — the same class of trust this project already extends to
  website-exact-match today, but government IDs are more failure-prone
  when sourced from OCR/scraped data (a plausible future Phase 2
  provider input). Mitigated by the Validation-layer format check
  proposed in Section 7 — a malformed identifier should never reach
  the dedup tier at all.
- **Company-level email dedup risk**, if adopted against this
  document's recommendation: shared/generic inboxes could incorrectly
  merge genuinely distinct legal entities (franchise/reseller
  structures especially). This is the reasoning behind Section 7's
  recommendation to exclude email from company-level matching entirely.
- **Configuration-quality risk, not a code risk:** a poorly-tuned custom
  weight set (e.g. all weight on one factor) produces confident-looking
  but poorly-calibrated scores. No backend fix addresses this — it's a
  future UX concern (e.g. a live preview showing how weight changes
  would re-score existing prospects), out of this phase's backend
  scope, flagged so it isn't forgotten.
- **Scope discipline:** the CEO's brief says "VAT, registration number,
  website, domain, company name, etc." — "website"/"domain" are the
  same existing signal, and "etc." is open-ended. This proposal treats
  VAT + registration number + the re-ordered existing website/fuzzy-name
  tiers as the actual Phase 1b deliverable, and defers any further,
  currently-unnamed signal to a future addition — keeping this sub-phase
  bounded and reviewable, consistent with this project's "small
  reviewable commits" discipline.

---

## Consolidated list of design decisions to reconsider before implementation

1. **Email as a company-level dedup key: recommend NO** — keep it as
   `Prospect` data only, excluded from `find_duplicate()`'s matching
   logic; real email-based matching, if ever wanted, belongs at the
   `ProspectContact` (person) level as a separate future concern.
2. **The 5-factor default weight split is not decided here** — Section
   8's table is illustrative only; needs explicit CEO input before
   implementation, since it changes every future Prospect's effective
   scoring.
3. **Custom `scoring_weights` validation: recommend strict, at write
   time** (must sum to 100, keys must be a subset of the five known
   factors) rather than silent rescaling or unchecked sums.
4. **`dedup.py`'s purity: recommend one new, separate DB-touching
   function** for the indexed identifier lookup, rather than either (a)
   changing `find_duplicate()`'s existing pure signature, or (b) doing
   the identifier check via the same in-memory scan as fuzzy-name
   matching (simpler, but forgoes the indexing win).
5. **Manual-provider extension: recommend yes** — add `vat_number`/
   `registration_number` to `RawProviderResult`, `ManualCSVProvider`,
   and the frontend's `CandidateBuyerRow` form in this same phase, so
   the new dedup tier is genuinely end-to-end testable before Phase 2's
   real provider exists, not just unit-testable.
6. **Re-scoring existing prospects after new weights/factor ship:
   recommend no** — leave historical `score_breakdown` frozen as
   recorded; new weights/factor apply only to future scoring passes.

No code has been written. Waiting for approval on the above — in
particular items 1–2 and 5, which materially affect what gets built —
before implementation begins.
