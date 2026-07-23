# Dashboard capabilities architecture review — Sales Pipeline, Pipeline Overview, Revenue Pipeline, AI Recommendations, Mailbox Brief, Open Conversations

**Status:** design guidance only, produced at the CEO's explicit request,
before any implementation. Nothing in this document is authorized for
implementation — same proposal → refinement → explicit-approval process
every prior milestone in this project (M0–M8) went through. This document
does not assign milestone numbers (e.g. "M9", "M10") — M9 is already
reserved elsewhere (Organization & AI Workforce Management, referenced by
`deferred-items-and-design-boundaries.md` and the interim `/auth/register`
admin gate) and this work's actual sequencing relative to that is the
CEO's call, not something to presume here. Milestones below are labeled
`Track C1`–`Track C5` purely as internal cross-references within this
document.

**Method:** every claim about "this already exists" or "this doesn't
exist" below was verified by reading the real code — every file in
`app/models/`, the relevant route files, `app/models/enums.py` in full,
and the current frontend placeholder components — not assumed from the
dashboard mockups alone. Several of the six widgets turned out to be far
closer to done than their placeholder text implies; two are genuinely
greenfield. Getting this distinction right is the entire point of doing
this review before writing code, since it changes both the build order
and which milestones actually need a migration.

---

## 0. Executive summary of findings

Before designing anything new, here is what already exists for each of
the six capabilities, confirmed by reading the real code:

| Capability | Backend reality today |
|---|---|
| **Open Conversations** | Fully modeled. `Conversation` (migration 0009, M6.1) has `company_profile_id`, `status` (`ConversationStatus.OPEN`/`CLOSED`). `GET /company-profiles/{id}/conversations?status=open` (`app/api/routes/conversations.py`) already exists, already tenant-scoped via `get_owned_company_profile`, already registered in `app/main.py`. **Nothing new to build except a KPI-shaped aggregation and frontend wiring.** |
| **AI Recommendations** | Fully modeled. `Recommendation` (M2/M3) is real, with `recommendation_type`/`confidence`/`status`/evidence. `GET /company-profiles/{id}/prospects/{prospect_id}/recommendations` already exists — but only per-prospect. **The one real gap is a cross-portfolio aggregation endpoint** (`AiRecommendations.tsx`'s own docstring already correctly diagnoses this, including the N+1 trap of faking it client-side). |
| **Mailbox Brief** | The data it would summarize already exists (`Conversation`, `EmailMessage`, `reply_intelligence` classification) and the `conversations` router is registered (`MailboxBrief.tsx`'s docstring claiming otherwise is now stale — see finding below). **What's missing is the synthesis step itself**: an on-demand AI-generated executive summary, per the design already approved in principle by `future-milestones.md` note 9 and `m6-reply-intelligence-plan.md`'s Decision Point 0. |
| **Sales Pipeline** | Nothing. No Opportunity/Deal model, no monetary field, anywhere in `app/models/`. The only adjacent concept is the legacy, deprecated `Company.stage: PipelineStage` (M0-era, tenant-unscoped, explicitly "dormant" per `OutreachDraftStatus`'s own docstring) — already correctly rejected as a data source by `SalesPipelineWidget.tsx`'s own docstring. **Genuinely new domain.** |
| **Pipeline Overview** | Same gap as Sales Pipeline — a different visualization (conversion funnel) of the same underlying opportunity data, not a second independent gap. `RelationshipStage` (`COLD→CONTACTED→ENGAGED→QUALIFIED→NEGOTIATION`, already live on `Prospect`, already advanced by `app/crm_automation/state_machine.py`) is the closest existing concept, but it has no monetary value, no WON/LOST terminal state, and is explicitly documented as "account-level sales history," a different thing from a deal-stage funnel. |
| **Revenue Pipeline** | Same gap again — needs the same new model's monetary field, aggregated. Confirmed: no product/company/prospect model anywhere has a price, deal value, or currency field today (`Product` has no pricing field at all). |

**One documentation-consistency finding surfaced by this review, unrelated
to any of the six capabilities' actual backend gap:** `MailboxBrief.tsx`'s
docstring states "no `conversations` router is registered in
`app/main.py`." That was true when M6.5 hadn't shipped yet; it registers
today (`app/main.py` line 242,
`app.include_router(conversations.router, prefix=API_PREFIX)`), confirmed
by grep. The real gap for Mailbox Brief was never the router — it's the
missing synthesis endpoint. Track C4 below includes correcting this
docstring as part of its own scope, not as a separate fix, since touching
that file is already in scope there.

**What this means for build order:** three of the six placeholders (Open
Conversations, AI Recommendations, Mailbox Brief) require **zero new
database tables** — they're aggregation/synthesis endpoints over data
that already exists, tenant-scoping already solved by the existing
`get_owned_company_profile` dependency every other route in this codebase
uses. The other three (Sales Pipeline, Pipeline Overview, Revenue
Pipeline) all depend on **one new domain** — an Opportunity/Deal model —
that does not exist in any form today and is the one piece of this review
genuinely comparable in size to M1–M7's original engines. Building that
model is the load-bearing milestone; the three widgets that read from it
are three separate, smaller, independently reviewable slices on top of
one shared foundation — this is a *related*-capabilities grouping the
CEO's own "do not merge unrelated capabilities" instruction does not rule
out, since merging them into one shared schema is the whole point (three
divergent stage vocabularies for the same real-world concept would be a
new instance of the M0 `Company`/`Prospect` duplication mistake this
project has already spent real migration effort undoing — see
`deferred-items-and-design-boundaries.md` item 6).

---

## 1. Opportunity/Deal — the new foundational domain (Sales Pipeline, Pipeline Overview, Revenue Pipeline all depend on this)

### 1.1 Purpose

Model a real, monetary sales opportunity per Prospect: what stage it's at
(a deal-progression funnel distinct from `RelationshipStage`'s
"how warmed up is this relationship" and distinct from `ProspectStatus`'s
"where is this row in the Discovery→Qualification pipeline"), how much
it's worth, and whether/how it closed. This is the one real "we sell
things and need to track deals" concept the platform has never had — M1
through M7 built Discovery→Research→Personalization→Outreach→Delivery→
Reply Intelligence→CRM Automation, all of which precede a deal existing;
none of them represent the deal itself.

### 1.2 Backend architecture

A new `app/opportunities/` package, mirroring the shape of
`app/crm_automation/`: a pure `state_machine.py` (deterministic stage
transitions + won/lost terminal logic, zero DB access, unit-testable with
no fixtures — same discipline as
`app/crm_automation/state_machine.py`), a `service.py` (the only writer —
never the frontend, same "system-generated, UI only ever reads" boundary
`Task` already established), and `app/api/routes/opportunities.py` for
CRUD + the two aggregation endpoints Pipeline Overview and Revenue
Pipeline need. No new AI engine, no new background worker for the model
itself — creation/stage-advancement is either a direct user action (an
API call from a future Opportunity UI, not built in this review's scope)
or a deterministic side effect of an existing event (e.g. a `Task`
resolution), never a new autonomous AI pipeline. This keeps Opportunity
squarely in the same "deterministic system of record" category as `Task`,
not a new engine alongside Discovery/Research/Personalization/Outreach.

### 1.3 Database schema

```
opportunities
  id                    UUID PK
  company_profile_id    UUID NOT NULL FK -> company_profiles.id ON DELETE CASCADE
  prospect_id           UUID NOT NULL FK -> prospects.id         ON DELETE CASCADE
  prospect_contact_id   UUID NULL      FK -> prospect_contacts.id ON DELETE SET NULL
  name                  VARCHAR(255) NOT NULL   -- e.g. "Acme Corp - Q3 textile order"
  stage                 opportunity_stage ENUM NOT NULL DEFAULT 'qualified_lead'
  amount                NUMERIC(14,2) NULL      -- see 1.11 on NUMERIC vs Float
  currency              VARCHAR(3) NULL         -- ISO 4217, e.g. "USD" - nullable until an amount exists
  probability           FLOAT NULL              -- 0-100, optional AI- or user-estimated close likelihood
  expected_close_date   DATE NULL
  closed_at             TIMESTAMPTZ NULL
  lost_reason           VARCHAR(500) NULL       -- only meaningful when stage = closed_lost
  source_task_id        UUID NULL FK -> tasks.id ON DELETE SET NULL  -- provenance, mirrors Task.source_event_type's honesty
  created_at / updated_at   TimestampMixin (existing project convention)

opportunity_stage_history      -- append-only, same discipline as OutreachEdit/OutreachEvidence
  id                    UUID PK
  opportunity_id        UUID NOT NULL FK -> opportunities.id ON DELETE CASCADE
  from_stage            opportunity_stage ENUM NULL   -- NULL only for the row created at Opportunity creation
  to_stage              opportunity_stage ENUM NOT NULL
  changed_by_user_id    UUID NULL FK -> users.id ON DELETE SET NULL
  changed_at            TIMESTAMPTZ NOT NULL
```

`opportunity_stage` enum — deliberately matching the CEO's own worked
vocabulary from the dashboard concepts (`Qualified Lead → Meeting →
Sample → Quotation → Negotiation → Purchase Order → Customer`) rather
than reusing `RelationshipStage` or `PipelineStage`, because both of
those are proven-wrong precedents for this exact job (`RelationshipStage`
is explicitly "account-level sales history," not a deal funnel, and has
no WON/LOST; `PipelineStage` is the dormant, tenant-unscoped legacy
model). Two closed terminal values are added
(`CLOSED_WON`/`CLOSED_LOST`) that none of the existing stage enums have,
since a deal funnel without a real "did it close" outcome can't produce
a conversion rate — the entire point of the Pipeline Overview widget:

```python
class OpportunityStage(str, enum.Enum):
    QUALIFIED_LEAD = "qualified_lead"
    MEETING = "meeting"
    SAMPLE = "sample"
    QUOTATION = "quotation"
    NEGOTIATION = "negotiation"
    PURCHASE_ORDER = "purchase_order"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"
```

### 1.4 API endpoints

- `POST /company-profiles/{id}/opportunities` — create, scoped via the
  existing `get_owned_company_profile` dependency, `prospect_id` must
  belong to the same profile (same `_get_prospect_or_404` pattern
  `prospect_contacts.py` already uses).
- `GET /company-profiles/{id}/opportunities` — list, filterable by
  `stage`/`prospect_id`, same query-param convention as
  `list_prospect_contacts`/`list_conversations`.
- `GET /company-profiles/{id}/opportunities/{opportunity_id}` — detail.
- `PATCH /company-profiles/{id}/opportunities/{opportunity_id}` — update
  name/amount/currency/probability/expected_close_date only; **stage
  changes go through a dedicated endpoint below, never this one** —
  mirrors why `ProspectContact`'s archive/unarchive are their own POST
  routes rather than folded into the generic `PUT`, so a stage
  transition is always auditable and always produces a
  `opportunity_stage_history` row, never silently.
- `POST /company-profiles/{id}/opportunities/{opportunity_id}/advance-stage`
  — body `{ to_stage, lost_reason? }`; validates the transition through
  `state_machine.py` (e.g. reject skipping straight to `CLOSED_WON` from
  `QUALIFIED_LEAD` unless explicitly allowed — a real design decision
  Track C2 below should settle, not invent silently), writes the history
  row, sets `closed_at` when entering either closed state.
- `DELETE /company-profiles/{id}/opportunities/{opportunity_id}` —
  RESTRICT-protected from the start (never CASCADE-then-fix-later): an
  Opportunity with any `opportunity_stage_history` row is real execution
  history under this project's own platform-wide lifecycle rule
  (`deferred-items-and-design-boundaries.md`'s generalized rule from the
  ProspectContact/DiscoverySearch fixes) — archive, not hard delete, is
  the right default here from day one. This is the one place this
  review's design pre-empts a mistake this project has already made and
  fixed twice (Discovery Search, then ProspectContact) rather than
  waiting for a third RESTRICT-migration fire drill.
- `GET /company-profiles/{id}/opportunities/funnel` — Pipeline Overview's
  own endpoint: one query, `GROUP BY stage`, `COUNT(*)`, returning stage
  order + counts + conversion percentage stage-to-stage. A dedicated
  endpoint rather than making the frontend compute this from the raw
  list, same "don't push aggregation logic onto the client" principle
  `topPerformingCountries`/`aggregateByCountry` already follow for
  World Map/Top Countries.
- `GET /company-profiles/{id}/opportunities/pipeline-value` — Revenue
  Pipeline's own endpoint: `SUM(amount)` over open (non-closed) stages,
  plus a separate `SUM(amount) WHERE stage = 'closed_won'` for "won this
  period" if the CEO wants that distinction — a single-purpose read
  endpoint, not folded into the funnel endpoint above, since a KPI card
  needs one number fast and the funnel needs a full breakdown; conflating
  the two would make the KPI strip's own perf budget depend on the
  heavier funnel query.

### 1.5 Service layer

`app/opportunities/service.py`: `create_opportunity`, `advance_stage`
(the only path that ever writes `stage` + a history row, called by the
route above and available for a future automatic trigger — e.g. CRM
Automation's `state_machine.py` gains a rule that suggests, never
auto-executes, an Opportunity stage advance from a `Task` resolution,
mirroring the existing "no rule ever advances a Prospect into NEGOTIATION
automatically" restraint already documented for `RelationshipStage`),
`compute_funnel(company_profile_id)`, `compute_pipeline_value
(company_profile_id)`. Deliberately no AI content-generation call
anywhere in this service — Opportunity is data-entry + deterministic
transitions, not a synthesis domain.

### 1.6 Background workers

None required for the model itself. If a future milestone wants an AI
suggestion ("this Opportunity looks stalled, nudge it") that would be a
new, separately-scoped Workflow Engine action (same registration pattern
as `discovery_execution_action.py`/`personalization_execution_action.py`
in `app/workflow_actions/`) triggered off a real Event
(`opportunity.stage_unchanged_for_N_days` or similar) — explicitly out of
this review's scope; noted here only so a future session knows where it
would plug in without redesigning this schema.

### 1.7 AI agent interactions

None in this initial slice. Opportunity is deliberately a plain CRM
record, not an AI-generated one — the same reason `Task.suggested_action`
is written by a deterministic rule (`app/crm_automation/state_machine.py`)
rather than an LLM call. If a future milestone wants AI-estimated
`probability` or an AI-suggested `amount` from Personalization/Research
context, that's an additive field-population job, not a redesign of this
table — same "additive, not a schema fight" pattern
`OutreachContext`/`future-milestones.md` note 5 already established for
similar future-AI-enrichment asks.

### 1.8 Required models

New: `Opportunity`, `OpportunityStageHistory`, `OpportunityStage` enum.
Touches (read-only, no column changes) existing: `Prospect`,
`ProspectContact`, `CompanyProfile`, `Task` (optional `source_task_id`
FK), `User` (optional `changed_by_user_id` FK on history rows).

### 1.9 Relationships with existing M0–M8 architecture

`Opportunity.prospect_id` is mandatory, same "every M1+ entity anchors to
a real Prospect, never the legacy Company" discipline every table since
M1 already follows. Deliberately does **not** touch `RelationshipStage`
(stays exactly what it is — an account-warmth signal CRM Automation
already advances) or `ProspectStatus` (Discovery/Qualification pipeline
position) — Opportunity is a third, genuinely distinct axis
("is there a monetary deal, and where is it"), not a relabeling of either
existing one. This is the same "two axes that look similar but answer
different questions, kept separate rather than collapsed" reasoning
`BuyerReadinessLevel` vs `RelationshipStage` already documents in
`app/models/enums.py`.

### 1.10 Security and multi-business considerations

Every route above goes through `get_owned_company_profile`, the same
dependency `prospects.py`/`prospect_contacts.py`/`conversations.py`
already use — no new isolation mechanism to invent, no risk of repeating
the legacy `Company`/`Contact` tenant-unscoped mistake, since Opportunity
is a first-class M8-era table from birth, never adjacent to the legacy
CRM. `source_task_id`/`changed_by_user_id` both `SET NULL` on delete
(never `RESTRICT`), consistent with every other "who did this" audit FK
in this codebase (`ProspectContact.archived_by_user_id`,
`Task.assigned_user_id`).

### 1.11 Performance considerations

`opportunities.company_profile_id`, `.stage`, `.prospect_id` all indexed
(matching every other tenant-scoped table's own indexing convention).
The funnel/pipeline-value endpoints are both single-table `GROUP BY`/
`SUM` queries with no joins required for the aggregate itself — cheap
even at real scale, and each is its own endpoint specifically so the KPI
strip's `pipeline-value` call never pays for the funnel's full breakdown.
`amount` uses `NUMERIC(14,2)`, not `Float` (unlike `Prospect.total_score`/
`Company.legitimacy_score`, which are legitimately approximate AI scores)
— this is real money; floating-point rounding error on a currency column
would be a genuine, avoidable correctness bug this review should not
wave through just because the rest of the schema uses `Float` for scores.

### 1.12 Future scalability through M10

The `opportunity_stage_history` table (append-only, same discipline as
`OutreachEdit`) is what lets a future Analytics milestone compute real
win-rate/velocity/stage-duration metrics without redesigning anything —
exactly the same bet `OutreachRun`'s frozen `config_snapshot` already
made for outreach analytics. `currency` being a real column (not assumed
single-currency) means a future multi-currency rollup (relevant given
this platform's own textile-export/multi-country framing — see
`WorldMap`/`CountryIntelligencePanel`) is an aggregation-layer addition,
not a migration. The explicit non-goal for this slice: no forecasting,
no weighted-pipeline AI model, no multi-user deal ownership/assignment
(that's M9 Organization & AI Workforce Management's territory — same
`assigned_user_id`-style anticipatory-but-unused field could be added to
`Opportunity` at that time, the same zero-migration-later bet `Task`
already made).

---

## 2. Sales Pipeline (Zone 2 flagship widget)

### 2.1 Purpose
A compact, at-a-glance stage-box view of the current Opportunity pipeline
— literally the dashboard's flagship "where are our deals" surface the
concept renders always implied should exist, per `SalesPipelineWidget.tsx`'s
own docstring history.

### 2.2 Backend architecture
No new backend beyond Section 1 — this widget is a pure consumer of
`GET /company-profiles/{id}/opportunities/funnel` (or a lighter
stage-count-only projection of it, if the box-per-stage UI needs less
than the full conversion-rate breakdown Pipeline Overview needs — a
frontend-shape decision, not a new backend endpoint).

### 2.3 Database schema
None new — reads `opportunities`/`opportunity_stage_history` from
Section 1.

### 2.4 API endpoints
Reuses Section 1.4's funnel endpoint. No dedicated endpoint of its own
unless the box UI's exact data shape ends up meaningfully different from
the funnel's — decide at implementation time by comparing the two
components' real prop needs, not preemptively.

### 2.5 Service layer
None new.

### 2.6 Background workers
None.

### 2.7 AI agent interactions
None.

### 2.8 Required models
None new.

### 2.9 Relationships with existing M0–M8 architecture
Same Zone 2 slot the dashboard has reserved for it since M8.3; only the
data source changes from "honest placeholder" to "real Opportunity
aggregation."

### 2.10 Security and multi-business considerations
Inherits Section 1.10 entirely — no separate concern.

### 2.11 Performance considerations
Same endpoint as Pipeline Overview if reused as-is; if a lighter
stage-count-only variant is built instead, that's strictly cheaper, never
more expensive.

### 2.12 Future scalability through M10
None beyond Section 1.12 — this is a presentation layer over that
foundation.

---

## 3. Pipeline Overview (Zone 3 funnel chart)

### 3.1 Purpose
The Discovered→Researched→Outreach→Replied→Negotiation→Won-shaped
conversion funnel `PipelineFunnel.tsx`'s own docstring already describes
as the honest gap — a different visualization of the same Opportunity
data as Sales Pipeline (full funnel + stage-to-stage conversion
percentages, not just current stage-box counts).

### 3.2 Backend architecture
Consumes Section 1.4's `GET .../opportunities/funnel` directly — this
endpoint's conversion-percentage computation (not just raw counts) is
scoped to Pipeline Overview specifically, since Sales Pipeline may not
need it.

### 3.3 Database schema
None new.

### 3.4 API endpoints
`GET .../opportunities/funnel` (Section 1.4) — one shared endpoint for
both Sales Pipeline and Pipeline Overview is correct here (unlike merging
unrelated capabilities, this is the SAME data at two granularities of
presentation, the textbook case for one endpoint + two frontend views).

### 3.5 Service layer
`compute_funnel` (Section 1.5) — conversion-rate math (stage N count /
stage N-1 count) lives here, not duplicated in two frontend components.

### 3.6 Background workers
None.

### 3.7 AI agent interactions
None in this slice. A future "AI explains why conversion dropped at
stage X" narrative would be a distinct, separately-scoped addition (same
category as `Recommendation.rationale`), not built here.

### 3.8 Required models
None new beyond Section 1.

### 3.9 Relationships with existing M0–M8 architecture
Restores the Design Bible Section 8 requirement `CommandCenter.tsx`'s own
docstring already tracks as "restored as an honest placeholder, real data
pending this exact milestone."

### 3.10 Security and multi-business considerations
Inherits Section 1.10.

### 3.11 Performance considerations
Single `GROUP BY` query; conversion percentages computed in Python over
the (small, per-business) grouped result — no N+1, no cross-business
scan.

### 3.12 Future scalability through M10
Same as Section 1.12; additionally, a time-boxed funnel ("this month's
cohort") is a natural, additive future filter on the same endpoint
(`created_at`/`closed_at` range params) — not a schema change.

---

## 4. Revenue Pipeline (Zone 1 KPI card)

### 4.1 Purpose
A single headline number — total open pipeline value (and optionally
won-this-period value) — for the KPI strip.

### 4.2 Backend architecture
Consumes Section 1.4's `GET .../opportunities/pipeline-value`.

### 4.3 Database schema
None new.

### 4.4 API endpoints
`GET .../opportunities/pipeline-value` (Section 1.4), deliberately
separate from the funnel endpoint per that section's own performance
reasoning.

### 4.5 Service layer
`compute_pipeline_value` (Section 1.5).

### 4.6 Background workers
None.

### 4.7 AI agent interactions
None.

### 4.8 Required models
None new beyond Section 1.

### 4.9 Relationships with existing M0–M8 architecture
Sits in the KPI strip next to Active Prospects/AI Confidence
Score/Needs Review/AI Tasks Running/Open Conversations — the last
KPI-strip placeholder this review resolves.

### 4.10 Security and multi-business considerations
Inherits Section 1.10. One additional consideration specific to a
monetary KPI: currency mixing. If a business's opportunities carry
different `currency` values, `SUM(amount)` across them is meaningless
without conversion — Track C3 (Section 8 below) must decide up front
whether to (a) require one currency per business at the `CompanyProfile`
level for this initial slice (simplest, matches this platform's current
single-business-per-profile framing) or (b) show a per-currency
breakdown instead of one summed number. This should be settled during
Track C3's own review, not discovered as a bug after ship.

### 4.11 Performance considerations
Single `SUM()` aggregate query, cheap at any realistic per-business
opportunity volume.

### 4.12 Future scalability through M10
Real multi-currency rollup (FX-rate-aware conversion to one reporting
currency) is the natural extension once real multi-currency businesses
exist — additive, not a redesign, per Section 1.12.

---

## 5. AI Recommendations (Zone 3 card)

### 5.1 Purpose
A cross-portfolio "what should we act on across every prospect" feed —
the aggregate view `AiRecommendations.tsx`'s own docstring already
correctly identifies as the one missing piece.

### 5.2 Backend architecture
One new read endpoint in the existing
`app/api/routes/recommendations.py` — no new package, no new model. The
existing per-prospect `list_recommendations` stays exactly as-is (still
used by whatever prospect-detail view calls it today); this is an
additive sibling route, not a replacement.

### 5.3 Database schema
None new. `Recommendation` (Section 0 table) already has every field this
needs (`status`, `recommendation_type`, `confidence`, `created_at`,
`prospect_id`).

### 5.4 API endpoints
`GET /company-profiles/{id}/recommendations` — cross-portfolio, one real
SQL join (`Recommendation` → `Prospect` filtered by
`Prospect.company_profile_id`), never the N+1 fan-out
`AiRecommendations.tsx`'s docstring explicitly and correctly ruled out.
Supports the same `status`/`recommendation_type` filters the per-prospect
route already does, plus a `limit` (mirroring `TodaysPriorities`/
`ActivityTimeline`'s own `limit`/`compact` convention for bottom-row
cards) and default sort `created_at DESC`.

### 5.5 Service layer
Thin — a single parameterized query, no new service module needed;
follows the existing pattern where simple list endpoints live directly
in the route file (see `list_prospect_contacts`) rather than always
requiring a separate service layer. If future logic (e.g. de-duplicating
near-identical recommendations across prospects, or ranking by
confidence × recency) grows past "one query," extract to
`app/research/recommendation_service.py` at that time — not preemptively.

### 5.6 Background workers
None — `Recommendation` rows are already written by the existing
Research/Personalization engines; this milestone only reads them
differently.

### 5.7 AI agent interactions
None new — no AI call in this endpoint itself, since it's reading
already-AI-generated rows, not generating anything new.

### 5.8 Required models
None new.

### 5.9 Relationships with existing M0–M8 architecture
Pure read-side extension of M2/M3's existing `Recommendation` model — the
least architecturally risky of all six capabilities in this review, since
no new table, enum, or FK is introduced at all.

### 5.10 Security and multi-business considerations
The join must filter through `Prospect.company_profile_id`, not just
"any Recommendation" — get this filter wrong and it's a direct
cross-tenant data leak (worse than the already-accepted legacy
Company/Contact gap, since this would be a NEW code path, not a
grandfathered one). Use the same `get_owned_company_profile` dependency
every other route already relies on; do not hand-roll a second isolation
check.

### 5.11 Performance considerations
One join + `LIMIT`, indexed on `Recommendation.prospect_id` (already
indexed) and `Prospect.company_profile_id` (already indexed) — cheap.
This is exactly the query the N+1 alternative was trying to avoid.

### 5.12 Future scalability through M10
A future "AI Recommendations" page (not just the dashboard card) would
add pagination/sort options to the same endpoint — additive query params,
not a new table.

---

## 6. Mailbox Brief (Zone 3 card)

### 6.1 Purpose
An on-demand, AI-generated executive summary of a connected mailbox —
deals in progress, important replies, new leads, stalled conversations,
suggested next actions — exactly the feature `future-milestones.md` note
9 originally specified and `m6-reply-intelligence-plan.md`'s Decision
Point 0 confirmed supersedes that note's storage model (persistent
Conversation/EmailMessage, not the original's "never persist" design) while
explicitly carrying its privacy constraints forward.

### 6.2 Backend architecture
A synthesis endpoint, not a new domain package: reads already-existing
`Conversation`/`EmailMessage`/reply-intelligence classification for one
`company_profile_id`, assembles a bounded context (most recent N
conversations, capped, not the whole mailbox history), and makes one
`app/ai_gateway` call (same client abstraction
Personalization/Outreach/Research already use — `ai_gateway/client.py` +
`providers/{claude,openai,gemini}_client.py`) to produce the summary.
Lives in a new `app/mailbox_brief/` package with one `service.py`
(`generate_brief(db, company_profile_id) -> MailboxBriefResult`) — kept
separate from `app/reply_intelligence/` since that package's job is
per-message classification, not portfolio-level synthesis; conflating the
two would blur a boundary this project has been careful about everywhere
else (Research vs. Personalization vs. Outreach are kept separate for the
identical reason).

### 6.3 Database schema
Per the privacy constraint carried forward from `future-milestones.md`
note 9 ("must not introduce a table that caches fetched email bodies or
threads beyond the single request/response cycle"), no new table is
strictly required for a v1 that regenerates on every click. If the CEO
wants a "last brief" to persist across page reloads (reasonable UX ask),
the **only** thing that should be stored is the AI-generated summary
output itself, never raw message content:

```
mailbox_briefs
  id                    UUID PK
  company_profile_id    UUID NOT NULL FK -> company_profiles.id ON DELETE CASCADE
  summary               TEXT NOT NULL          -- the AI's generated brief, not raw email content
  generated_at          TIMESTAMPTZ NOT NULL
  conversation_count     INTEGER NOT NULL       -- how many conversations fed this brief, for transparency
```

This table is explicitly optional for Track C4 (Section 8) — decide
whether v1 needs persistence at all before writing this migration; a
stateless "regenerate on click" v1 needs zero new schema.

### 6.4 API endpoints
`POST /company-profiles/{id}/mailbox-brief/generate` — a POST, not a GET,
deliberately: this is an action with a real cost (an LLM call) and a
real privacy posture ("the mailbox is read only in response to an
explicit user click," per the carried-forward constraint), not an
idempotent read — matches the existing convention of using POST for
Discovery/Research/Personalization/Outreach "run" actions
(`run_search`, etc.) for the identical reason. If persistence (6.3) is
built: `GET /company-profiles/{id}/mailbox-brief` to fetch the last saved
one without regenerating.

### 6.5 Service layer
`app/mailbox_brief/service.py`: `generate_brief()` — assembles context
(bounded conversation window), builds the prompt (via
`app/prompt_builder`, the same shared prompt-construction module
Personalization/Outreach already use — never a hand-rolled f-string,
matching this project's own established discipline), calls
`app/ai_gateway`, returns the structured result. No new AI provider
integration — reuses the existing gateway entirely.

### 6.6 Background workers
None — explicitly on-demand only, per the carried-forward privacy
constraint ("never continuously or on a schedule"). This is the one
capability in this review where NOT building a worker is a deliberate,
load-bearing design decision, not an oversight — a scheduled/background
version would violate the already-approved privacy posture.

### 6.7 AI agent interactions
The one genuinely new AI-generation call among all six capabilities.
Structured similarly to `PersonalizationSnapshot`/`OutreachDraft`
generation: a real `ai_gateway` call, a real prompt built from real
context, with the same "AI-attributed, always `accent-ai`/purple in the
UI" semantic this project already applies everywhere (Design Bible
Section 4.1) — the Mailbox Brief card itself, once real, should likely
gain the same `glow`/AI-attribution treatment `AiPipelineWidget`/
`AiWorkforceStatusWidget` already carry, not just the ambient accent
color it has today as a placeholder.

### 6.8 Required models
New (optional, see 6.3): `MailboxBrief`. No changes to `Conversation`/
`EmailMessage`.

### 6.9 Relationships with existing M0–M8 architecture
Pure read-and-synthesize consumer of M6's Conversation/EmailMessage/reply
intelligence work — no new relationship to Discovery/Research/
Personalization/Outreach/Delivery required, since a mailbox brief is
about replies and relationship state, not outbound generation.

### 6.10 Security and multi-business considerations
Must only ever read conversations scoped to the requesting user's own
`company_profile_id` (same `get_owned_company_profile` dependency).
Additionally carries the privacy constraints `future-milestones.md` note
9 already specified as binding, not optional: no CRM writes as a side
effect of generating a brief (no auto-created contacts/tasks/opportunities
— even though Section 1's new Opportunity model now exists, a brief must
never auto-create one; that stays a separate, explicit user action, same
"nothing is written without a separate, explicit user action per item"
rule already on record), and the UI must clearly indicate when the
mailbox is actively being accessed (a loading/generating state, not a
silent background fetch).

### 6.11 Performance considerations
The LLM call itself is the dominant cost, same order of magnitude as
Personalization/Outreach's own generation calls — bound the input context
(cap conversation/message count fed into the prompt) the same way
`PipelineFunnel`'s query is bounded, so cost/latency stay predictable
regardless of how large a mailbox grows.

### 6.12 Future scalability through M10
Once Section 1's Opportunity model exists, a later version could
cross-reference "conversations with no matching Opportunity" as a
suggested-action category — additive, not a redesign. Multi-mailbox
businesses (more than one `ProviderConnection`) would need the context
assembly to span connections, not just conversations — a service-layer
change, not a schema change, since `Conversation.provider_connection_id`
already exists.

---

## 7. Open Conversations (Zone 1 KPI card)

### 7.1 Purpose
A single headline count — how many conversations are currently open —
for the KPI strip.

### 7.2 Backend architecture
No new backend package. Either (a) the frontend calls the existing
`GET .../conversations?status=open` and takes `len(...)` client-side —
acceptable ONLY if the result set is bounded/paginated so this never
becomes an unbounded fetch masquerading as a KPI, or (b) — the
recommended choice — add one lightweight count endpoint, matching this
review's own "don't push aggregation onto the client" principle applied
consistently to Sections 1–6.

### 7.3 Database schema
None new.

### 7.4 API endpoints
`GET /company-profiles/{id}/conversations/count?status=open` (or a
query-param variant of the existing list route that returns `{"count":
N}` when a `count_only` flag is set) — smallest possible new surface
area of any capability in this review.

### 7.5 Service layer
None new — a single `COUNT(*)` query, inline in the route, same
"simple enough to not need a service module" reasoning as Section 5.5.

### 7.6 Background workers
None.

### 7.7 AI agent interactions
None.

### 7.8 Required models
None new.

### 7.9 Relationships with existing M0–M8 architecture
Pure read extension of M6.1's `Conversation` model — no new relationship
to anything.

### 7.10 Security and multi-business considerations
Same `get_owned_company_profile` scoping the existing `list_conversations`
already uses — zero new isolation surface.

### 7.11 Performance considerations
The cheapest possible query in this entire review — `COUNT(*) WHERE
company_profile_id = ? AND status = 'open'`, on an already-indexed
column.

### 7.12 Future scalability through M10
None beyond what M6 already built. This capability requires no forward
design work at all — it's finished the moment the count endpoint and its
frontend wiring exist.

---

## 8. Dependency graph and optimal build order

```
                     ┌─────────────────────────────┐
                     │  Section 1: Opportunity      │
                     │  domain (new model,          │
                     │  migration, service, 5 routes)│
                     └───────────┬─────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
      Sales Pipeline     Pipeline Overview     Revenue Pipeline
        (Section 2)          (Section 3)          (Section 4)

  AI Recommendations (Section 5) ── independent, zero new schema
  Open Conversations (Section 7) ── independent, zero new schema
  Mailbox Brief (Section 6)      ── independent, zero new schema,
                                     but the single largest AI-integration
                                     effort of the three independent ones
```

Sales Pipeline, Pipeline Overview, and Revenue Pipeline cannot start
before the Opportunity model (Section 1/Track C3) exists — building any
one of them first would either mean inventing a throwaway ad-hoc schema
now and migrating it later (exactly the M0 `Company`/`Prospect`
duplication mistake this project has already paid down once) or blocking
on the same foundational work anyway. AI Recommendations, Mailbox Brief,
and Open Conversations have no dependency on Section 1 or on each other
and can be built in any order, in parallel with Section 1 and with each
other.

**Recommended order, smallest/lowest-risk first:**

1. **Track C1 — Open Conversations** (Section 7): smallest possible
   change in this entire review, zero schema, proves the "wire a real
   KPI number into the strip" pattern end-to-end for the two KPI cards
   that follow it later (Revenue Pipeline reuses the exact same
   frontend wiring shape).
2. **Track C2 — AI Recommendations** (Section 5): one new endpoint, zero
   schema, slightly more involved than C1 (a real join, not a bare
   count) but still no migration and no AI call.
3. **Track C3 — Opportunity domain** (Section 1): the one genuinely
   foundational milestone — new tables, new enum, new service, five new
   routes. Reviewed and approved on its own before any of Sections 2–4
   are touched, since getting the stage vocabulary and the RESTRICT/
   archive decision wrong here would ripple into three consumer
   milestones instead of one.
4. **Track C4 — Sales Pipeline + Pipeline Overview + Revenue Pipeline**
   (Sections 2–4), only after Track C3 lands: three small, independently
   reviewable slices (each is "one frontend component + one existing
   endpoint from Track C3," not three more migrations), which can
   genuinely be three separate pull requests/reviews even though they
   share one prerequisite milestone. Could also run as three parallel
   sub-tracks (C4a/C4b/C4c) once C3 is merged, since none of the three
   depends on either of the others.
5. **Track C5 — Mailbox Brief** (Section 6): scheduled last not because
   it's hardest technically, but because it's the only capability that
   introduces a brand-new AI-generation call and a genuinely new privacy
   surface (an on-demand mailbox read) — worth landing once the smaller,
   lower-risk milestones have already re-established a clean rhythm of
   real, verified ships after this review. Has zero dependency on Tracks
   C1–C4 and could technically be pulled earlier if the CEO wants the AI
   capability sooner; the ordering above is a risk/complexity
   recommendation, not a hard technical constraint.

---

## 9. Milestone breakdown

### Track C1 — Open Conversations
- **Scope:** one new count endpoint; frontend `KpiStrip.tsx`/`KpiCard.tsx`
  wiring (remove the `placeholderKind="not-implemented"` prop, pass a
  real fetched value, matching how Active Prospects/AI Confidence
  Score/Needs Review already work).
- **Files affected:** `app/api/routes/conversations.py` (add one route),
  `frontend/src/dashboard/KpiStrip.tsx`, possibly a new
  `useOpenConversationsCount` hook mirroring `useDashboardPortfolio`'s
  own shape.
- **Migration requirements:** none.
- **Testing strategy:** one new backend test (real DB, real route call,
  same convention as `test_track_b2_verification.py`) confirming the
  count only reflects the caller's own `company_profile_id` and only
  `status='open'` rows; `tsc -b --force` for the frontend change.
- **Verification plan:** a `verify_*.sh`-style script or an addition to
  an existing one, hitting the real endpoint against a seeded
  Conversation fixture; manual browser check that the KPI card shows a
  real number instead of "Not yet implemented."
- **Rollback:** revert the frontend prop change (falls back to the
  placeholder instantly) and/or remove the one new route — no migration
  to reverse, the lowest-risk rollback of any track in this plan.

### Track C2 — AI Recommendations
- **Scope:** one new cross-portfolio endpoint in
  `recommendations.py`; `AiRecommendations.tsx` wired to a real fetch
  with a `limit`, matching `TodaysPriorities`/`ActivityTimeline`'s
  existing `limit`/`compact` convention.
- **Files affected:** `app/api/routes/recommendations.py`,
  `frontend/src/dashboard/AiRecommendations.tsx`, a small
  `useRecommendationsPortfolio` (or similar) hook.
- **Migration requirements:** none.
- **Testing strategy:** a real-DB test confirming the join is correctly
  scoped by `company_profile_id` (the cross-tenant-leak risk Section
  5.10 flags explicitly) using two different businesses' prospects in
  the fixture, the same "prove isolation with two owners" pattern
  `test_track_b2_verification.py`'s legacy-gap tests already established.
- **Verification plan:** same shape as Track C1's script; explicitly
  re-verify no N+1 query pattern was introduced (a single query plan
  check, or a straightforward query-count assertion in the test).
- **Rollback:** same low-risk shape as Track C1 — no migration involved.

### Track C3 — Opportunity domain
- **Scope:** the full Section 1 design — `Opportunity`,
  `OpportunityStageHistory`, `OpportunityStage` enum, migration,
  `app/opportunities/` package (`state_machine.py`, `service.py`),
  five routes (`create`, `list`, `get`, `update`, `advance-stage`,
  `delete`, `funnel`, `pipeline-value` — eight total, corrected count
  from Section 1.4). No frontend changes in this track — Sections 2–4's
  widgets are explicitly Track C4, kept separate so this migration can
  be reviewed purely on its schema/API merits.
- **Files affected:** new `app/models/opportunity.py`,
  `app/models/opportunity_stage_history.py`, an addition to
  `app/models/enums.py`, new `app/opportunities/__init__.py`,
  `state_machine.py`, `service.py`, new
  `app/api/routes/opportunities.py`, a new Alembic migration, router
  registration in `app/main.py`.
- **Migration requirements:** one new migration creating both tables
  and the `opportunity_stage` Postgres enum type — the single largest
  schema change in this entire plan, and the only one requiring a real
  `alembic revision` review (upgrade/downgrade pairing checked the same
  way Track A's own migration review already checks every prior
  migration in this codebase).
- **Testing strategy:** unit tests for `state_machine.py` (zero
  fixtures, pure value transformations — same shape as
  `test_crm_automation_state_machine.py`), real-DB tests for the service
  layer and every route (create/list/advance-stage/RESTRICT-delete/
  funnel/pipeline-value), explicitly including a test that a stage
  regression or an invalid transition (e.g. `CLOSED_WON` →
  `QUALIFIED_LEAD`) is rejected by the state machine, not silently
  allowed by the route.
- **Verification plan:** a new `verify_track_c3.sh` (or milestone-numbered
  equivalent once the CEO assigns one), following the exact
  `verify_*.sh` conventions this codebase already has 19 examples of —
  boot, migrate, run the test suite, a direct `pg_constraint` check that
  the delete-RESTRICT FK is actually in place (mirroring
  `verify_track_b2.sh`'s own pg_constraint check pattern).
- **Rollback:** the migration's `downgrade()` drops both new tables and
  the enum type cleanly (no other table has a FK pointing at
  Opportunity yet, so this is a clean, low-collateral rollback) — but
  once Track C4 ships and any real Opportunity rows exist in a real
  deployment, rolling back this migration would destroy real pipeline
  data, so rollback is "clean, cheap, and safe" only in the window
  before Track C4's widgets go live and real users start entering deals
  — worth stating explicitly rather than assuming migrations are always
  freely reversible once real data exists.

### Track C4 — Sales Pipeline, Pipeline Overview, Revenue Pipeline (three sub-tracks, all depend on Track C3)
- **Scope (C4a — Sales Pipeline):** wire `SalesPipelineWidget.tsx` to
  Track C3's funnel/stage-count endpoint.
- **Scope (C4b — Pipeline Overview):** wire `PipelineFunnel.tsx` to the
  same funnel endpoint's fuller conversion-rate payload.
- **Scope (C4c — Revenue Pipeline):** wire the Revenue Pipeline KPI card
  to Track C3's pipeline-value endpoint; resolve the currency-mixing
  question (Section 4.10) before this sub-track is considered done, not
  after.
- **Files affected:** `frontend/src/dashboard/SalesPipelineWidget.tsx`,
  `PipelineFunnel.tsx`, `KpiStrip.tsx`/`KpiCard.tsx` — no backend files,
  assuming Track C3 already shipped everything these three need.
- **Migration requirements:** none (all consumed from Track C3).
- **Testing strategy:** `tsc -b --force` per sub-track; a frontend-side
  check (manual or automated, depending on what test tooling exists by
  the time this is built) that each widget's real data matches what
  Track C3's own tests already proved the endpoint returns.
- **Verification plan:** manual browser check per sub-track — each of
  the three placeholder cards should show real data with no console
  errors, the same Group 2 "Command Center dashboard" manual-check
  convention `comprehensive-verification-matrix.md` row 18 already uses.
- **Rollback:** revert each widget's frontend change independently — the
  three sub-tracks' rollbacks are fully independent of each other, since
  none of the three writes to the backend or to each other.

### Track C5 — Mailbox Brief
- **Scope:** `app/mailbox_brief/` package (`service.py`, prompt
  construction via `app/prompt_builder`), one new POST endpoint (plus
  optional GET if persistence is chosen), the optional `mailbox_briefs`
  table if persistence is chosen (decide before writing the migration,
  not after), `MailboxBrief.tsx` wired to a real "Generate" action
  (button-triggered, not auto-fetched on page load — matching the
  carried-forward "only in response to an explicit user click"
  constraint), and the stale-docstring correction noted in Section 0.
- **Files affected:** new `app/mailbox_brief/__init__.py`/`service.py`,
  possibly `app/models/mailbox_brief.py` + a migration if persisted, new
  `app/api/routes/mailbox_brief.py`, router registration in
  `app/main.py`, `frontend/src/dashboard/MailboxBrief.tsx`.
- **Migration requirements:** none if v1 is stateless (regenerate on
  every click); one small migration (single table) if persistence is
  chosen.
- **Testing strategy:** a real-DB test asserting the context-assembly
  step only pulls conversations for the correct `company_profile_id`
  (same isolation-proof pattern as Track C2), and — since this is the one
  track making a real AI Gateway call — the same kind of provider-call
  test the existing Personalization/Outreach test suites already use
  (mocking/stubbing the AI Gateway call itself, not a live provider call
  in CI, matching this project's own established "no live AI provider
  call in any verify script" disclosure convention).
- **Verification plan:** manual verification is unavoidable for the
  actual AI output quality (same honest limitation every AI-generation
  milestone in this project has disclosed — M3/M4's own verify scripts
  never assert on generated prose content, only on the pipeline
  producing *some* well-formed output); a `verify_*.sh` addition can
  still mechanically confirm the endpoint returns a 200 with a non-empty
  summary against a real seeded mailbox.
- **Rollback:** revert the frontend wiring back to the placeholder;
  drop the new migration (if persistence was chosen) only if no real
  briefs have been generated and saved yet — otherwise archive, don't
  drop, per this project's own platform-wide lifecycle rule.

---

## 10. Explicit non-goals for this review

Not designed here, deliberately: multi-user deal ownership/assignment
(M9's territory), AI-estimated deal probability/amount (a future additive
enrichment per Section 1.7), scheduled/recurring Mailbox Briefs (ruled out
by the carried-forward privacy constraint, not an oversight), a dedicated
Opportunity management UI beyond the three dashboard widgets (list/detail/
edit views would be a natural follow-on but are not one of the six
placeholders this review was scoped to), and multi-currency FX conversion
(Section 4.12's future extension, not this slice's job).

---

**This document presents architecture only. No migration, model, route,
service, or frontend code has been written as part of it. Waiting for
explicit approval — and, where flagged above (opportunity-stage
transition rules, currency-mixing handling, Mailbox Brief persistence
question), specific decisions — before Track C1 or any other track
begins.**
