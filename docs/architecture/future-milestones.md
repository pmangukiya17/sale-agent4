# Future milestones — architectural guidance

**Status:** design guidance only, recorded at the close of M4 (AI Outreach
Generation Engine). Nothing in this document is authorized for
implementation. Each item still requires its own architecture proposal,
refinement, and explicit approval before any code is written — the same
process M1 through M4 each went through.

**Why this document exists:** these are constraints the M4 architecture
was deliberately shaped to accommodate, so that M5–M7 don't force a
redesign of what's already built. They're recorded now, while the
reasoning is fresh, so a future session — human or AI agent — doesn't
have to rediscover it from scratch.

---

## 1. Campaign domain

A future `Campaign` domain should sit *above* `OutreachPlaybook`, not
replace or restructure it:

```
Campaign → Target Audience → Outreach Playbook → Outreach Requests
    → Drafts → Scheduling (M5) → Replies (M6) → Automation (M7) → Analytics
```

A Campaign is expected to eventually carry: name, description, objective,
target audience, an associated Outreach Playbook, success KPI(s), status,
budget (optional), owner (once multi-user exists), start/end dates, and
analytics/performance.

**Why the current architecture accommodates this:** every Outreach entity
(`OutreachRequest`, `OutreachJob`, `OutreachDraft`, `OutreachRun`) already
carries `prospect_id`/`prospect_contact_id`/`company_profile_id` denormalized
down the full chain, purely so a parent scope can filter without joining
back up through every table. A `campaign_id` would follow the identical
convention — a new table, one nullable foreign key propagated the same
way. Target-audience resolution (a fixed list vs. dynamic criteria) mirrors
the pattern already used by `ICPCriteria` and `DiscoverySearch.query_spec`.
No existing table's meaning needs to change.

**One nuance to carry forward:** `OutreachDraft.version` is scoped to
`(prospect_contact_id, channel_key)`, not to a campaign. If two campaigns
ever target the same contact on the same channel, their drafts share one
version counter for that contact rather than each campaign getting a
clean 1, 2, 3 sequence. `is_current` still resolves correctly either way,
but campaign-level draft history needs to filter by `campaign_id` and sort
by `created_at` rather than rely on a per-campaign version number.

---

## 2. AI Decision Gate

Before any draft reaches scheduling (M5), a future quality-control step
should answer "should we actually contact this prospect?" — producing a
recommendation (contact / wait), a confidence score, and structured
reasoning (ICP match, research confidence, buyer persona relevance,
communication strategy quality, duplicate-outreach detection).

**Why the current architecture accommodates this:** this is a new,
read-mostly decision record, not a change to anything upstream. It would
reference an `OutreachDraft` by id — the same relationship shape
`OutreachEvidence` already has to `OutreachDraft` — rather than embedding
new fields on the draft itself. `OutreachDraft.confidence` and `.reasoning`
already exist for the generation step; a Decision Gate is a distinct,
later evaluation step and should stay a separate record so the two are
never conflated.

---

## 3. User Decision Gate

Even when the AI recommends contacting a prospect, the human should retain
the final call, with a richer vocabulary than today's approve/reject:
Contact Now, Approve for Scheduling, Skip, Research Again, Save for Later,
Move to Nurture, Existing Customer, Blacklist, Wrong Contact, Not a Good
Fit. This decision should become part of the prospect's permanent history.

**Why the current architecture accommodates this:** `OutreachDraftStatus`
(draft / pending_approval / approved / rejected / superseded) is
deliberately narrow — a per-draft-version lifecycle, not a full decision
taxonomy. A richer user-decision vocabulary belongs in its own record
(alongside or replacing today's approve/reject actions), the same
append-only, never-overwritten discipline used by `OutreachEdit`. It
should reference the draft and, where the decision is about the
relationship rather than one specific draft (Blacklist, Existing
Customer), the prospect directly.

---

## 4. Decision history

Every outreach decision should be recorded permanently: prospect, AI
recommendation, AI confidence, user decision, reason, date, and eventual
outcome (reply received, meeting booked, deal won/lost). This is the
feedback loop that lets future agents answer questions like "how often did
the user disagree with the AI," "which playbooks perform best," and "which
CTAs generate the most meetings."

**Why the current architecture accommodates this:** this is a direct
extension of a discipline already used throughout the project —
`OutreachEdit`, `OutreachEvidence`, and every `*Run` table's frozen
`config_snapshot` are all append-only, immutable, evidence-linked records.
Decision history is the same pattern applied one layer higher (the
decision itself, not just the content). "Which playbooks perform best"
becomes a query over this history joined to `OutreachPlaybook`, not a new
capability that has to be designed in.

---

## 5. OutreachContext expansion

Before a real LLM powers Outreach generation, `OutreachContext` should
carry the complete business context, not only the `personalization_variables`
projection: Company Profile, Products, ICP, Knowledge Base, Intelligence
Snapshot, Signals, Recommendations, Personalization Snapshot,
Communication Strategy, and — once they exist — Outreach History and
Reply History.

**Why the current architecture accommodates this:** `OutreachContext`
today deliberately mirrors `PersonalizationContext`'s shape but is
narrower — it assumed Personalization had already pre-digested everything
Outreach needs. That assumption doesn't fully hold: Products, ICP, and
Knowledge Base are not currently loaded into `OutreachContext` at all,
which is a known, disclosed gap, not a design boundary. Closing it means
adding fields to one dataclass and a few more read queries in
`_build_context` — the same shape of change `PersonalizationContext`
already demonstrates is safe to make. No existing field or table changes
meaning.

---

## 6. Playbook intelligence

Instead of manually choosing a playbook, the AI should eventually be able
to recommend or select one automatically, using industry, buyer type,
relationship stage, communication strategy, buyer readiness, campaign
objective, and historical playbook performance — while staying
explainable rather than an opaque AI judgment call.

**Why the current architecture accommodates this:** `OutreachPlaybook`
already has a free-string `playbook_goal` for categorization. Explainable
(not opaque) selection implies matching against *structured* criteria, not
just an LLM reading prose — which points at adding a structured
`selection_rules` field to `OutreachPlaybook` (industries, buyer types,
relationship stages, and similar match criteria) that a scoring function
evaluates against the same context `OutreachContext` already assembles.
This is additive to the playbook record; it doesn't change how playbooks,
blocks, or requests relate to each other.

---

## 7. Long-term vision

The objective is not an AI email generator. It is an autonomous AI Sales
Operating System — specialized agents (Discovery, Research, Personalization,
Outreach, and eventually Scheduling, Reply Intelligence, and Follow-up
Automation) collaborating over a shared, explainable, versioned body of
business knowledge, with the human always able to see why an agent did
what it did and always retaining the final call. Every architectural
decision from M5 onward should be evaluated against this, not against
what's convenient for the next milestone alone.

This is also the standard the six notes above should be held to when they
eventually get proposed for real: does this keep the system explainable,
does it keep the human in control, and does it compose with what's already
built rather than working around it.

---

## 8. Business Branding

**Status: partially implemented at the close of M4 Finalization**, unlike
notes 1–6 above. Only the Email Signature module is real; everything else
in this section is still design guidance for later modules.

**What exists today:** `BrandEmailSignature` — a mutable, 1:1 row keyed by
`company_profile_id` (`app/models/brand_email_signature.py`,
migration `0007`), holding `signature_html` (rich HTML from a TipTap
editor), a server-derived `signature_plain_text`
(`app/branding/plain_text.py`), and `is_active`. Routes live under a
dedicated `/branding/company-profiles/{company_profile_id}/email-signature`
namespace (`app/api/routes/brand_email_signatures.py`) rather than nested
under `/company-profiles/{id}/branding/...`, so Branding reads as its own
domain in the API surface. The frontend page is
`/businesses/:companyId/branding/email-signature`
(`BusinessEmailSignature.tsx`), linked from the Businesses list.

**Governance principle — "Branding" is a UI/module concept, not a
database aggregate.** There is deliberately no `business_brandings` parent
table. Each branding category is its own table hanging directly off
`company_profile_id`, the same way `Product`/`ICPCriteria`/`KnowledgeBase`
already do. A future module (Identity, Visual, Social, Contact, Legal) is a
new sibling table added the same way — never a child row under a
`BrandEmailSignature`-like table, and never a new column bolted onto it.

**Governance principle — mutable-in-place, not versioned.** Unlike
`OutreachPlaybook`/`PromptVersion`/`PersonalizationSnapshot`,
`BrandEmailSignature` is edited via PUT in place, exactly like
`CompanyProfile` and `WorkspaceSettings`. It is business configuration
(fix a typo, update a title), not an evolving strategy that benefits from
a version history. Any future Branding module should default to this same
mutable-in-place discipline unless a concrete reason to version it
surfaces.

**Governance principle — explainability without versioning the source.**
Outreach never stores a foreign key to `BrandEmailSignature`. Instead,
`EmailChannelProvider.render()` freezes the exact rendered
`signature_html` into `OutreachDraft.ai_generated_content.assembled` as a
third, independent key (alongside `subject` and `body`, never concatenated
into `body`) at generation time — zero schema change to `OutreachDraft`,
since `assembled` was already documented as channel-shaped/free-form JSON.
This is the pattern any future Branding module should follow if its output
ever gets baked into a generated artifact (a PDF quotation, a brochure): freeze
the rendered value into that artifact's own generation-time record, don't
version the Branding table itself.

**Governance principle — one source of truth as Branding expands.**
`CompanyProfile` already holds `website`, `phone`, `email`, `address`, and
`logo_url`. The M0 `Company`/`Contact` vs. M1 `Prospect`/`ProspectContact`
split (two models for the same real-world concept, one stale and unwired)
is the cautionary precedent for what NOT to repeat here. When a future
Branding module overlaps an existing `CompanyProfile` field (e.g. a
future Identity module introducing its own `logo_url`), that same
milestone must, together: (a) backfill data from `CompanyProfile` into the
new table via migration, (b) mark the old `CompanyProfile` field's
docstring as superseded/backward-compatible-only, and (c) update
`CompanyProfileEditor.tsx` in that same milestone to stop exposing the
superseded field. All three together, in one milestone — never a
half-migrated dual source of truth left for a later cleanup pass.

**Deferred by explicit decision, not oversight:** logo upload (no real
file storage exists yet — the architecture doesn't block adding it later,
but Base64-in-the-database was deliberately rejected), a dedicated
Identity module (would today hold only a tagline — not enough
responsibility yet to justify a table; introduce it once real Visual
branding — logo, brand colors, typography — exists too), Visual, Social,
Contact, and Legal modules (contact/legal info in particular will need the
same-milestone `CompanyProfile` migration-cleanup described above once
built), and any Outlook/Gmail/scheduling/reply-tracking integration.
