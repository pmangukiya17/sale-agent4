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

---

## 9. AI Mailbox Brief (M6, manual-only by design)

**Status:** design guidance only, recorded during M5 planning at the
user's explicit request, purely so M5's provider layer doesn't need a
redesign to accommodate it later. Nothing here is authorized for
implementation — same rule as notes 1–8. This is part of M6 (Reply
Intelligence & Conversation Management), not M5.

**The feature:** a manually-triggered executive summary of a connected
mailbox — Business → Connected Mailbox → click "Generate Mailbox Brief" —
covering deals in progress, important customer replies, new leads,
customers awaiting a response, stalled conversations, high-priority
emails, meeting requests, RFQs, supplier updates, urgent issues, and
suggested next actions. The model is an AI sales manager giving a
briefing on request, not a system that watches the inbox.

**Privacy constraints — binding on whatever eventually implements this,
not optional hardening:** the mailbox is read only in response to an
explicit user click, never continuously or on a schedule; only the
minimum set of recent messages needed for that one brief is fetched;
email content is processed only to produce that brief and is not
retained afterward; nothing is written to the CRM (no contacts,
companies, deals, notes, or tasks) without a separate, explicit user
action per item (e.g. "Save Contact", "Create Opportunity", "Create
Task"); the UI must clearly indicate whenever the mailbox is actively
being accessed. In short: a temporary assistant invoked on request, never
a background observer, and never a system that accumulates long-term
knowledge from the mailbox on its own.

**Why the current M5 architecture already accommodates this — no
redesign needed:**

`ProviderConnection`/`ProviderCredential` (M5) already model "an
authorized grant to a mailbox with a recorded set of OAuth scopes,"
independent of what those scopes are used for. Reading is not a new
connection concept — it's a new *capability* requested against the same
connection concept M5 already has. `scopes_granted` (a JSONB list, already
on `ProviderConnection`) is exactly what lets M6 check "does this
connection have read access" before attempting to fetch anything.

The OAuth lifecycle M5 treats as first-class — Connect, **Reconnect**,
Disconnect, Verify — is exactly the mechanism M6 needs for *progressive*
scope consent, not an M5-only convenience. M5's own Connect flow should
request only send-scoped permissions (e.g. Gmail `gmail.send`, Graph
`Mail.Send`) — it has no reason to ask for more. M6 adds mailbox-read
scopes (`gmail.readonly`, `Mail.Read`) the first time a user clicks
"Generate Mailbox Brief" on a connection that doesn't have them yet, via
the same Reconnect operation and the same authorize-url builder — just a
different scope list passed in. No new OAuth plumbing, no new connection
table, no change to `ProviderConnection`'s shape.

At the provider-layer code level (M5 Layer 5, not yet written), providers
are **capability-based**, not assumed-uniform: a shared connection-
lifecycle contract (`get_authorize_url`/`exchange_code`/
`refresh_access_token`/`verify`) is common to every provider, but sending
and mailbox-reading are two separate capability interfaces
(`EmailSendCapable.send()`, `MailboxReadCapable.fetch_recent_messages()`)
that a concrete provider class opts into independently via Python's
ordinary multiple inheritance — it does not inherit a capability it
doesn't implement. `GmailProvider`/`OutlookProvider` implement both
(`class GmailProvider(EmailSendCapable, MailboxReadCapable)`); a future
SMTP/SES/SendGrid/Mailgun provider implements only `EmailSendCapable` and
is never forced to stub out a `fetch_recent_messages()` it has no way to
support. Code that needs to know whether a given connection's provider
can do something checks `isinstance(provider, MailboxReadCapable)` rather
than assuming every registered provider supports every capability. One
connection, one concrete class per provider, capabilities declared by
which interfaces that class actually implements — never a second parallel
"read provider" registry disconnected from the send one, and never a
capability every provider is forced to carry whether it applies or not.

**A guardrail for M6's own future schema, stated now so it isn't
discovered as a problem later:** because a brief is ephemeral by
requirement, M6 must not introduce a table that caches fetched email
bodies or threads beyond the single request/response cycle that produces
one brief. Whatever table(s) M6 does add should hold only the AI-generated
summary output (if the user explicitly chooses to keep it) or the results
of an explicit save action (a saved Contact, a created Opportunity, a
created Task) — never raw mailbox content sitting in the database on the
strength of an AI's judgment that it might be useful later. That would be
exactly the kind of long-term-knowledge accumulation the privacy
requirement above rules out, just moved into a different table.

**A known M5 limitation this milestone should revisit if it needs
threading:** `OutlookProvider.send()` (M5) always returns
`provider_message_id=None` because Graph's single-call `/me/sendMail`
endpoint doesn't return one (see the docstring in
`app/delivery/providers/outlook_provider.py` for the full explanation).
Gmail sends do return a real id. If M6 conversation threading needs a
stable Outlook message id to correlate a reply back to the outbound send,
the fix is to switch `OutlookProvider.send()` to Graph's
create-draft-then-send pattern (`POST /me/messages`, then
`POST /me/messages/{id}/send`) - a change local to that one method, not
to `EmailSendCapable`'s interface or to `DeliverySendOutcome`'s shape.
Not needed unless/until M6 actually requires it.
