# M6 — Reply Intelligence & Conversation Management: Architecture & Implementation Plan

**Status:** proposal only, produced before any M6 implementation. Nothing in
this document is authorized for implementation until it is explicitly
approved, per this project's standing discipline (see the root `README.md`
and every prior milestone's own architecture-review gate). No code has been
written for M6. This document supersedes `future-milestones.md` note 9 in
part — see **Decision Point 0** below, which must be resolved before
anything else here is approved.

**Revision history:**
- **Rev 1:** replaced Microsoft Graph specifics with a generic
  `EmailProvider` abstraction — Outlook/Graph is Provider #1, implemented
  as one adapter behind that abstraction, not a shape the rest of the
  system is built around. Section 3 was restructured from "Microsoft
  Graph integration" into "Provider Integration Layer," and the database
  schema (section 2) now stores generic provider metadata rather than
  Graph-flavored fields.
- **Rev 2 (this revision):** Decision Point 0 is resolved — the
  persistent conversation model is officially adopted (see below), and a
  Provider Capability Matrix (section 3a) and a phased M6.1-M6.6
  implementation plan (section 14) are added, mirroring the phase
  discipline M5 was built under.

---

## Decision Point 0 — RESOLVED: persistent conversation model officially adopted

`future-milestones.md` note 9 ("AI Mailbox Brief") was written during M5
planning, specifically to define M6's shape *before* M5's provider layer
was built. It committed to a narrow, privacy-constrained design: mailbox
read access triggered only by an explicit user click, nothing fetched
except what one summary needs, no persistent storage of raw mailbox
content.

**This is now formally superseded.** The persistent design this document
proposes — `Conversation`, `EmailMessage`, `ConversationParticipant`,
`MailboxSyncState`, a background inbox-sync worker — is adopted as M6's
actual architecture, not the narrower manual/ephemeral brief. This is a
deliberate product decision, made explicitly and on the record here,
not a silent overwrite of the earlier commitment: note 9's design cannot
produce the reply-analysis history, timeline view, or CRM-updating
pipeline sections 4-6 require, and the long-term AI Sales OS vision
(`future-milestones.md` note 7, and the CRM → ... → Conversation
Intelligence → Workflow Automation progression this project is building
toward) depends on durable conversation state, not a one-shot summary.

**What replaces note 9's old safeguards, now that the constraint they
protected is gone:**
- Read access remains strictly opt-in per connection, via Reconnect,
  never granted implicitly (this part of note 9 is *not* superseded —
  it's a generically useful safeguard regardless of persistence, kept
  fully intact by section 3).
- First sync is bounded to a fixed recent window, not full mailbox
  history (section 3) — persistence doesn't mean unbounded retention.
- Attachment bodies are never stored, only metadata, fetched on demand
  (section 2) — the one place this document keeps note 9's "don't
  accumulate what nobody asked for" spirit literally, even though
  message bodies themselves are now persisted.
- A disconnect-and-purge action that actually deletes
  `Conversation`/`EmailMessage` rows for a connection is a **required**
  part of M6, not optional hardening (already flagged in section 11,
  reaffirmed here as binding now that this decision is final).

`future-milestones.md` note 9 should be marked superseded-by-M6 in that
document itself once this plan is approved, so a future reader doesn't
find two live, contradictory commitments. Alternative A in section 13
(ship the smaller ephemeral brief first) remains recorded for the
historical record but is no longer the live recommendation — this
decision closes that question.

---

## 1. High-level architecture

**What M6 is.** Reply Intelligence & Conversation Management: read inbound
mail from a connected mailbox, reconstruct conversations, classify and
extract structured information from replies with AI, surface it to the
user, and update CRM state — all without ever sending anything itself, and
all **independent of which email provider the mailbox happens to be**.

**The core design commitment: email, not Outlook.** Everything above the
provider-adapter boundary — conversation building, message
deduplication, thread reconstruction, AI classification/extraction, CRM
updates, the frontend — operates on a generic, provider-neutral data
model (section 2) and never references Microsoft Graph, Gmail, or IMAP
concepts directly. Outlook is Provider #1, implemented as one concrete
adapter behind an `EmailProvider` interface that already exists in this
codebase in nascent form (`app/delivery/providers/base.py`'s
`EmailConnectionProvider`/`EmailSendCapable`/`MailboxReadCapable`
capability classes, built in M5 specifically so this extension would be
additive — see section 3). Gmail becomes Provider #2 by implementing that
same interface; nothing above it changes.

**How it fits into M0–M5.** M6 is a new, sixth domain module, structurally
parallel to Delivery (M5): it owns its own tables, its own background
worker(s), its own API routes, its own frontend pages — and it reads from,
but never writes to, the domains beneath it.

```
Discovery (M1) → Research (M2) → Personalization (M3) → Outreach (M4)
    → Delivery (M5) → Reply Intelligence (M6)
```

Concretely, M6 reads:
- `ProviderConnection` (M5) — which mailboxes exist, their OAuth
  credentials via the existing `CredentialStore`, their granted scopes.
  Already provider-neutral: `ProviderConnection.provider_key` is a plain
  string (`"outlook"`, `"gmail"`, ...), not an enum tied to one vendor.
- `DeliveryQueueItem` (M5) — what was sent, to whom, from which
  `SendingProfile`/`DeliveryCampaign`/`OutreachDraft` — the correlation
  key for "this inbound message is a reply to that outbound send," itself
  already provider-neutral.
- `Prospect` / `ProspectContact` (M1) — identity resolution: match an
  inbound sender's email address to a known contact.

M6 writes:
- Its own new, provider-neutral tables (section 2).
- `Prospect.relationship_stage` (already exists, already documented as
  "M4-M7 are what advance it" — M6 is the first milestone to actually
  write it) and two new nullable columns, `last_contacted_at`/
  `last_replied_at`.
- `ProspectTimelineEvent` rows (existing table, new `event_type` values
  only — zero schema change, see section 5).

**Responsibilities.** Inbox sync (read-only access via a provider
adapter), thread reconstruction, AI classification/extraction, CRM signal
updates, recommended-next-action surfacing, conversation UI — none of
which know or care which provider a given mailbox uses.

**Boundaries — what M6 explicitly does not do.**
- M6 never sends email. That capability is `EmailSendCapable`, exclusively
  M5's. M6 only ever touches read/sync capabilities.
- M6 never auto-executes anything on the CRM beyond the specific,
  narrow writes listed above. It produces *recommendations*; a human
  acts on them — the same "AI recommends, human decides" principle
  already established for Outreach approval and specified for the future
  Decision Gate work in `future-milestones.md` notes 2-3. It does not
  advance `DeliveryCampaign`/`DeliveryQueueItem` state, create/edit
  `OutreachDraft` rows, or touch `CompanyProfile`/`SendingProfile` —
  mirroring the "point up, never down" discipline `DeliveryQueueItem`'s
  own docstring already establishes for the M4→M5 boundary.
- **Provider-specific logic never leaks above the adapter boundary.**
  No table, service, queue, or frontend component outside
  `app/delivery/providers/<provider>_provider.py` may reference Graph
  endpoints, Gmail API shapes, or IMAP protocol details. If a piece of
  conversation-building, AI, or CRM logic seems to need to know which
  provider it's dealing with, that's a signal the adapter interface is
  missing something and needs to grow a new method — not a signal to add
  an `if provider == "outlook"` branch outside the adapter. This is a
  hard architectural rule for M6, not a preference.

**Future compatibility.** The capability-based provider pattern was built
in M5 specifically so M6 is additive: a provider class opts into a read/
sync capability via ordinary multiple inheritance, nothing about
`EmailSendCapable` or the OAuth lifecycle changes. This plan extends that
pattern (section 3) and holds every other layer to it.

---

## 2. Database design

Six new tables, plus two additive nullable columns on existing tables.
Nothing existing is altered in shape or meaning. Every new table is
provider-neutral: provider identity is data (a string column), never
encoded into a table name, column name, or enum tied to one vendor.

### `Conversation`

One durable thread, scoped to a business relationship, not a mailbox or a
provider.

- `id`, `company_profile_id`, `prospect_id`, `prospect_contact_id`
  (nullable — see identity resolution below)
- `provider_connection_id` — which connected mailbox this conversation
  was observed through (a mailbox has exactly one provider, via
  `ProviderConnection.provider_key`, but `Conversation` itself stores no
  provider-specific field — provider identity lives on `EmailMessage`,
  per-message, since a conversation-building step could in principle
  correlate messages later observed through a different reconnected
  mailbox)
- `subject` — normalized (stripped of `Re:`/`Fwd:` prefixes) for display
- `conversation_key` — our own provider-agnostic derived correlation key,
  computed by the conversation-builder (section 3's thread-detection
  logic), not any one provider's native thread id verbatim. Stored as its
  own column since it must stay stable once assigned, independent of
  which provider-native ids (if any) contributed to computing it
- `status` — `open` / `stalled` / `closed` (derived by a scheduled
  freshness check, not written by AI directly)
- `last_message_at`
- `first_discovered_at`

**Why scoped to `(prospect, contact)`, not to a provider or mailbox:** a
conversation is about the *relationship*, not which mailbox or vendor you
happen to be reading it through this week. If a connected mailbox is ever
reconnected, disconnected and replaced, or the business switches from
Outlook to Gmail entirely, conversation history must survive that change
unaffected — this is the concrete test of "provider-agnostic" applied to
this table.

**Why `prospect_contact_id` is nullable:** an inbound message might come
from an email address that doesn't match any known `ProspectContact` yet.
The conversation still needs to exist so the message isn't dropped;
identity resolution is a separate, explicit step (section 4).

### `EmailMessage`

One row per individual email, inbound or outbound. This is the table
that carries provider identity as data — exactly the generic metadata
set requested:

- `id`, `conversation_id`
- `provider` — string (`"outlook"`, `"gmail"`, `"imap"`, ...), copied from
  `ProviderConnection.provider_key` at ingest time so this row is
  self-describing even if the connection is later disconnected or
  reconnected under a different provider
- `provider_connection_id`
- `provider_message_id` — the provider's own id for this message (Graph
  message id, Gmail message id, an IMAP `UID`+mailbox composite, ...) —
  nullable, since not every provider/every code path guarantees one (see
  the Outlook adapter note in section 3)
- `provider_thread_id` — the provider's own native thread/conversation id
  when it has one (Graph `conversationId`, Gmail `threadId`) — nullable,
  since some providers (plain IMAP has no native concept) never supply
  one; the conversation-builder treats this as one input signal, never
  the only one
- `internet_message_id` — the RFC 5322 `Message-ID` header. The
  universal, provider-independent identity: every provider's underlying
  transport is still SMTP-descended email, so this header exists (or is
  mintable, for a future SMTP-based send adapter) regardless of which
  API delivered the message. This is the dedup key (section 3)
- `in_reply_to`, `references` — raw header values, RFC 5322, present for
  any provider
- `direction` — reuses the existing `MessageDirection` enum
  (`app/models/enums.py`); provider-agnostic already
- `delivery_queue_item_id` — nullable FK to `DeliveryQueueItem`, set only
  when this row is the observed copy of something M5 sent; provider-
  agnostic (M5's own `DeliveryQueueItem` is already provider-neutral)
- `from_email`, `from_name`, `subject`, `body_text`, `body_html`
- `sent_at` / `received_at` — when the message was actually sent/received,
  per its own headers/provider timestamp
- `synced_at` — when *our* sync worker actually pulled this row in,
  distinct from `sent_at`/`received_at`; needed because sync can lag
  (polling interval, backlog, retries) and some downstream logic (e.g.
  "how fresh is our view of this mailbox") needs to reason about sync
  latency independent of message age
- `has_attachments` (bool)
- `is_analyzed` (bool, default false)

**Why `provider` is a plain string column here, not an enum or a
provider-specific table per vendor:** identical reasoning already used
for `ProviderConnection.provider_key` and `ProspectSource.provider_key`
in this codebase — adding a provider is a data-level change (a new
adapter class registered in a dict), never a schema migration to widen an
enum. This table's shape does not change when Gmail or IMAP support is
added; only a new row's `provider` value does.

### `ConversationParticipant`

- `id`, `conversation_id`, `email`, `name`, `role` (`to` / `cc` / `from`),
  `prospect_contact_id` (nullable — resolved or unresolved)

Provider-agnostic by construction — participants are identified by email
address, which means the same thing regardless of provider.

**Why its own table, not a JSONB list on `Conversation`:** real B2B export
deal threads (this app's own domain) routinely have multiple stakeholders
CC'd in and out over time. A real table lets identity resolution be
corrected per-participant later without rewriting a JSONB blob, and lets
the frontend query "which conversations include this contact" with an
index.

### `Attachment`

- `id`, `email_message_id`, `filename`, `content_type`, `size_bytes`,
  `provider_attachment_id`

Metadata only — no binary content stored, fetched from the provider
adapter on demand only when a user opens one. `provider_attachment_id` is
opaque, provider-defined (a Graph attachment id, a Gmail attachment id,
an IMAP part number) — the fetch-on-demand call is routed through the
same adapter that owns the connection, never interpreted generically
above that layer.

### `ReplyAnalysis`

**NOT BUILT in M6.4 — see "Reply Intelligence — as built (M6.4)" in
section 4.** M6.4 was explicitly scoped to extend `Conversation` with
four current-state fields instead of a separate per-message analysis
table. Left below as the original design in case a future milestone
revisits per-message analysis history.

One row per analyzed inbound `EmailMessage` — the AI output. Entirely
provider-agnostic: it operates on `EmailMessage.body_text`/`body_html`,
never on anything provider-specific.

- `id`, `email_message_id` (unique — one current analysis per message,
  re-analysis creates a new row and marks the old superseded, same
  discipline as `OutreachDraft.is_current`/`SUPERSEDED`)
- `prompt_version_id` — FK to the existing `PromptVersion` table
- `intent` — enum (`interested` / `not_interested` / `question` /
  `objection` / `negotiation` / `out_of_office` / `bounce` /
  `unsubscribe` / `other`)
- `sentiment` — enum (`positive` / `neutral` / `negative`)
- `urgency` — enum (`low` / `medium` / `high`)
- `extracted_data` — JSONB: buyer requests, product mentions, quantity,
  incoterms, destination country, certifications requested, questions
  asked
- `confidence`, `reasoning`, `model_used`

### `MailboxSyncState`

One row per `ProviderConnection` that has mailbox-read scope granted.
Renamed from this document's own earlier `InboxSyncState` at M6.2
approval time — the sync state belongs to the provider mailbox as a
whole, not only its Inbox folder; tracking Sent/Drafts/Archive per
connection later is then a `folder` column addition (or a second table)
on this same concept, never a rename.

- `id`, `provider_connection_id` (unique)
- `cursor` — opaque, provider-defined sync position (a Graph delta link,
  a Gmail `historyId`, an IMAP `UIDNEXT`/mailbox-state token). Named
  generically on purpose — the previous draft of this document called
  this `delta_link`, a Graph-specific term; nothing above the provider
  adapter interprets this value, it is only ever passed back into the
  same adapter that produced it. As built (M6.2), this is a `Text`
  column with no length cap or structural assumption — see "Synchronization
  Cursor Contract — as built" below for exactly what Outlook stores in it.
- `last_synced_at`, `last_sync_status` (`ok` / `error`),
  `last_sync_detail`
- `attempt_count` — consecutive failed-tick counter, reset to 0 on the
  next `ok` tick. Added during M6.2 implementation, not in this
  document's original field list — declared for a future backoff policy
  to read; nothing in M6.2 itself changes polling behavior based on it
  yet.
- `sync_window_start` — the earliest date this connection was ever synced
  from (bounded first-sync window, section 3)

### `Task`

The "recommended next action" concept. Entirely provider-agnostic —
operates on `Prospect`/`ReplyAnalysis`, never on provider data directly.

- `id`, `prospect_id`, `reply_analysis_id` (nullable)
- `suggested_action` — text
- `status` — `pending` / `done` / `dismissed`
- `created_at`, `resolved_at`

**Why its own table, not reuse of `ProspectTimelineEvent`:** a timeline
event is an immutable log entry; a task is a mutable, actionable item
with a lifecycle. Related (resolving a task should append a timeline
event), not the same thing.

### Additive columns (no new table)

- `Prospect.last_contacted_at`, `Prospect.last_replied_at`
- `ProspectContact.last_contacted_at`, `ProspectContact.last_replied_at`

### Relationship diagram (textual)

```
CompanyProfile ──< ProviderConnection ──< MailboxSyncState (1:1)
      (provider_key: "outlook" | "gmail" | "imap" | ... — data, not schema)
                          │
                          └──< EmailMessage >── Conversation ──< ConversationParticipant
                             (provider: string,       │
                              provider_message_id,     └── Prospect / ProspectContact
                              provider_thread_id,
                              internet_message_id,
                              in_reply_to, references,
                              direction, synced_at)
                                    │
                                    ├──< Attachment
                                    ├── ReplyAnalysis (versioned via is_current-style latest)
                                    └── DeliveryQueueItem (nullable, outbound correlation only)

ReplyAnalysis ──< Task ── Prospect
```

Nothing in this diagram, or in any table above it, names or assumes
Outlook. The word "Graph" does not appear in this section, and should
never appear in a migration file for these tables.

---

## 3. Provider Integration Layer

This section replaces what the first draft called "Microsoft Graph
integration." That framing was itself the mistake this revision corrects
— Graph is one provider's transport, not the general problem. This
section describes the `EmailProvider` abstraction all sync logic is built
against, with Graph/Gmail/IMAP specifics pushed down into adapters that
implement it.

### The interface boundary

M5 already declared the right shape for this
(`app/delivery/providers/base.py`), specifically so M6 wouldn't need to
redesign it:

```
EmailConnectionProvider   — OAuth/credential lifecycle (every provider)
EmailSendCapable          — send() (M5, Outlook + Gmail today)
MailboxReadCapable        — fetch_recent_messages(since, max_results)
                             (declared in M5, unimplemented — a one-shot,
                             time-windowed read, shaped for note 9's
                             original manual-brief use case)
```

**M6 adds one new capability interface, `IncrementalSyncCapable`,
alongside these rather than changing `MailboxReadCapable`:**

```
IncrementalSyncCapable
    fetch_messages_incremental(credential_payload: dict, cursor: str | None, max_results: int)
        -> IncrementalSyncResult(messages: list[RawEmailMessage],
                                  next_cursor: str | None,
                                  has_more: bool)
```

As built (M6.2), the first parameter is `credential_payload: dict` (the
same decrypted `{access_token, refresh_token, expires_at}` shape
`refresh_credential_if_needed` already produces for `EmailSendCapable.
send()`), not a `DeliveryContext`-style object — this document's earlier
draft used `context` generically before the shape was pinned down. Sync
has no queue item, no sending profile, no frozen content to carry; it
only ever needs a usable credential for one `ProviderConnection`, so the
signature is intentionally narrower than `send()`'s. `next_cursor` is
`str | None` (not `str`) because the very first tick for a brand-new
connection can, in principle, complete with nothing to advance to yet
(though Outlook's own implementation always returns a real link — see
below).

This is a distinct capability from `MailboxReadCapable` on purpose: a
one-shot "give me the last N messages" read (note 9's brief) and a
resumable, cursor-based incremental sync (M6's continuous background
sync) are genuinely different access patterns, not the same method
called twice. Keeping them separate means a future provider could
implement one without the other (e.g., a hypothetical read-only digest
API with no cursor concept), and means this M6 addition is purely
additive — `MailboxReadCapable` as declared in M5 is untouched.

`cursor` is opaque to every caller above the adapter: the inbox-sync-
worker persists whatever `next_cursor` a provider returns into
`MailboxSyncState.cursor` and passes it back unmodified on the next poll.
It never parses, compares, or reasons about the cursor's contents. This
is what makes `MailboxSyncState`'s schema provider-neutral (section 2) —
the column is a string; only the adapter that wrote it knows what's
inside.

`RawEmailMessage` is a small, adapter-produced, already-normalized
struct (from address, subject, body, headers including `Message-ID`/
`In-Reply-To`/`References`, provider message id, provider thread id if
any, sent/received timestamp, attachment metadata list) — the
conversation-builder (below) only ever consumes this normalized shape,
never a raw Graph/Gmail JSON payload. Normalization is the adapter's
job, done once, at the boundary.

### Provider adapters — where vendor specifics live, and nowhere else

```
class OutlookProvider(EmailConnectionProvider, EmailSendCapable,
                       IncrementalSyncCapable): ...   # Provider #1, M6
class GmailProvider(EmailConnectionProvider, EmailSendCapable,
                     IncrementalSyncCapable): ...     # Provider #2, additive
class IMAPProvider(EmailConnectionProvider, EmailSendCapable,
                    IncrementalSyncCapable): ...      # future, additive
class ExchangeProvider(EmailConnectionProvider, EmailSendCapable,
                        IncrementalSyncCapable): ...  # future, additive
```

Each adapter owns exactly its own vendor's sync mechanism behind the
identical `fetch_messages_incremental` signature:

- **Outlook (Graph):** delta query
  (`GET /me/mailFolders/inbox/messages/delta`); `cursor` = the FULL
  `@odata.nextLink` or `@odata.deltaLink` URL Graph itself returns (a
  directly-callable URL, not a hand-extracted `deltaToken`) — see
  "Synchronization Cursor Contract — as built" below for the precise
  mechanics; this is a slightly more literal choice than this document's
  original "`cursor` = `@odata.deltaLink`" framing, made because Graph's
  delta protocol is explicitly designed to be driven this way and it
  avoids any URL-parsing logic that could get subtly wrong.
- **Gmail:** `users.history.list`; `cursor` = Gmail's `historyId`.
- **IMAP (future):** no native delta concept — the adapter would
  implement incremental sync itself via `UID SEARCH`/`UIDNEXT` tracking,
  encoding whatever state it needs into the opaque `cursor` string. This
  is real, adapter-internal work a future IMAP provider must do; nothing
  above the interface needs to know or care that IMAP has no delta
  primitive.
- **Exchange (future, on-prem/EWS):** similarly adapter-internal —
  EWS has its own sync mechanism (`SyncFolderItems` with a sync state
  token), which maps onto the same opaque `cursor` contract.

**Adding Gmail requires implementing only `GmailProvider`.** No change to
the conversation builder, the AI pipeline, the CRM update logic, the
`MailboxSyncState`/`EmailMessage` schema, the mailbox sync worker's loop, or
any frontend component — all of which are written once, against
`IncrementalSyncCapable`/`RawEmailMessage`, never against a specific
vendor's shape. This is the concrete test of this document's stated
goal, and every section above and below this one is written to satisfy
it.

### Polling vs. webhooks — recommend polling for v1, provider-agnostic either way

Webhooks (Graph change notifications, Gmail push notifications via Cloud
Pub/Sub, EWS push notifications) exist in some form for most providers,
but each has a different registration/renewal/validation mechanism, all
of which require a publicly reachable HTTPS endpoint — infrastructure
this project doesn't have (dev is `docker compose` on `localhost`), and
none of which this sandbox has any way to test end-to-end. Polling via
`IncrementalSyncCapable` is the v1 recommendation for every provider
uniformly, not an Outlook-specific limitation — the interface is
designed so a webhook-based push mechanism could be added later as an
alternative trigger for the same conversation-building pipeline (a
webhook handler would just call the same ingest path a poll tick calls
today), without changing anything described in this section's interface
boundary.

### Sync strategy

Per `ProviderConnection` with read scope granted (requested via the
existing Reconnect flow — see below), the mailbox sync worker calls
`fetch_messages_incremental(cursor, max_results)` on an interval, using
`MailboxSyncState.cursor` as the resume position, for every connection
regardless of provider — one generic loop, no provider branching. First
sync (`cursor = None`) is bounded to a fixed recent window (e.g. the
last 30 days) by convention each adapter must honor internally, not
enforced by the worker.

### Synchronization Cursor Contract — as built (M6.2)

This section documents the concrete mechanism now that it exists, as a
permanent architectural reference — this is the answer to "how does sync
actually resume," pinned down precisely rather than left at the
provider-agnostic level the rest of this document deliberately stays at.

**1. Which Graph endpoint.** `GET /me/mailFolders/inbox/messages/delta`
(Inbox folder only — no other folder is synced in M6.2). The very first
call for a connection (`cursor is None`) adds `$filter=receivedDateTime
ge <30-days-ago>` to bound the initial backfill, plus `$select` for the
exact fields sync needs (`id,conversationId,internetMessageId,
internetMessageHeaders,from,subject,body,receivedDateTime,sentDateTime,
hasAttachments`) and `$top=<MAILBOX_SYNC_MAX_RESULTS_PER_TICK>`. Every
subsequent call is a plain `GET` of whatever URL the previous call
returned — no query parameters are reconstructed by this codebase on
later calls; Graph's own response URL already carries the filter/select/
top scope forward.

**2. What `MailboxSyncState.cursor` stores.** Neither a bare
`deltaToken` nor a hand-parsed value — the FULL `@odata.nextLink` or
`@odata.deltaLink` URL exactly as Graph returns it in the response body.
Both are complete, directly-callable Graph API URLs; a `deltaToken` (a
query parameter embedded inside a `deltaLink`) is never extracted or
handled separately. The column (`Text`, unbounded) does not care which
of the two it holds — see point 3.

**3. How the next sync knows where to continue.**
`OutlookProvider.fetch_messages_incremental` does exactly one thing with
a non-`None` cursor: `url = cursor`, then `GET` it. That's the entire
continuation logic. Which of the two Graph URL types was stored
determines what happens next, invisibly to our code:
   - If the stored value was a `@odata.deltaLink` (the tick before was
     fully caught up), Graph returns whatever changed since then, plus a
     new `@odata.deltaLink` (or a `@odata.nextLink` if the changes
     themselves span multiple pages).
   - If the stored value was a `@odata.nextLink` (the tick before left
     more pages unread), Graph returns the next page of that same
     backlog, plus another `@odata.nextLink` or, once exhausted, a
     `@odata.deltaLink`.

   `IncrementalSyncResult.has_more` is `True` exactly when the response
   carried `@odata.nextLink` — the sync worker does not loop within one
   tick to drain every page (a deliberate simplification, see
   `outlook_provider.py`'s module docstring); a large backlog is drained
   over several ticks instead, each advancing the cursor by one page.

**4. Is the cursor completely opaque to the sync engine?** Yes, with the
scope of "sync engine" precisely defined: `app/reply_intelligence/
sync_worker.py` and the `MailboxSyncState` model never inspect, decode,
parse, or branch on the cursor's contents — they only read it out of the
database, pass it unmodified into `fetch_messages_incremental`, and
write back whatever `next_cursor` comes out. The ONLY code in this
codebase that ever interprets the string is `OutlookProvider` itself
(and only in the trivial sense of using it directly as a request URL,
never parsing sub-fields out of it). This is the literal implementation
of the "opaque to everyone but its owner" discipline this document's
Database design section (2) already committed to before M6.2 existed.

**5. Does this abstraction support Gmail `historyId`, IMAP UID tracking,
and Exchange sync tokens without changing the sync worker?** Yes, and
this is the concrete test of that claim, not just an assertion:
`IncrementalSyncCapable.fetch_messages_incremental`'s signature types
`cursor` as a plain `str | None`, and `MailboxSyncState.cursor` is an
unstructured `Text` column — neither the interface nor the schema encodes
anything about URL shape, token format, or even single- vs.
multi-value state. Concretely, per provider:
   - **Gmail:** `cursor` would simply be the numeric `historyId` string
     returned by `users.history.list` — an even simpler case than
     Outlook's URL, fits the contract directly.
   - **Exchange (EWS):** `cursor` would be the base64 `SyncState` blob
     `SyncFolderItems` returns — also a single opaque string, fits
     directly.
   - **IMAP:** the one real nuance worth flagging explicitly, not
     glossing over — IMAP has no native single-token delta concept.
     Correct UID-based resumption needs TWO pieces of state together
     (`UIDVALIDITY`, which can change and invalidate all prior UIDs, plus
     the highest UID previously seen). A future `IMAPProvider` satisfies
     the contract by serializing both into the one opaque string itself
     (e.g. `json.dumps({"uidvalidity": ..., "last_uid": ...})`) — this is
     genuinely adapter-internal work, exactly as this document's
     "Provider adapters" section above already anticipated, and requires
     zero change to `sync_worker.py`, `MailboxSyncState`, or
     `IncrementalSyncCapable` itself.

   In every one of these cases, `sync_worker.py`'s `sync_one_connection`
   function is unmodified — it calls `provider.fetch_messages_incremental
   (credential_payload, sync_state.cursor, max_results)` and persists
   `result.next_cursor` verbatim, regardless of which provider produced
   either value.

**One honest limitation, disclosed rather than glossed over:**
`max_results` is only actually honored by Outlook's adapter on the FIRST
call for a connection (`$top` is baked into that call's URL). On every
subsequent tick, the URL Graph already handed back has its own page size
baked in from the original request — `max_results` passed on that call is
effectively inert for Outlook. This is a real, minor gap between the
interface's stated contract ("max_results is a hint honored per call")
and Outlook's actual behavior once cursor-based paging takes over; it
does not affect correctness (Graph still returns a bounded page every
time), but a future provider adapter is not guaranteed to honor
`max_results` identically on every call, and callers should not assume it
does.

**Also disclosed: the claiming pattern.** Section 7 (Background workers)
below describes a `SELECT ... FOR UPDATE SKIP LOCKED` claiming pattern,
mirroring `app/delivery/worker.py`. As actually built in M6.2, the
mailbox sync worker does NOT use that pattern — it runs a plain
sequential loop over every eligible connection within one process, no
row-level claiming. This mirrors the M5 Delivery worker's own current
reality (also a single, non-horizontally-scaled replica in
`docker-compose.yml` today) rather than the more defensive pattern this
document originally specified for M6. If the mailbox sync worker is ever
scaled to multiple replicas, adding `SKIP LOCKED`-style claiming on
`MailboxSyncState` at that point is additive, not a redesign — but it is
not present today, and this document should not claim otherwise.

### Requesting read access — provider-agnostic progressive consent

Every `EmailConnectionProvider` already shares one OAuth-lifecycle
contract (`get_authorize_url`/`exchange_code`/`refresh_access_token`/
`verify`) and the Reconnect operation that lets a connection request an
expanded scope list later. M6 read access is requested through that same
mechanism for every provider — `Mail.Read` for Outlook, `gmail.readonly`
for Gmail, an equivalent for any future provider — each adapter owns its
own scope-string vocabulary, and the Reconnect flow above it is
identical regardless of which strings it's passing through. No new OAuth
plumbing, no provider-specific route.

### Message deduplication — universal, not provider-dependent

Primary dedup key: `internet_message_id` (the RFC 5322 `Message-ID`
header), unique per `provider_connection_id`. This is deliberately *not*
`provider_message_id`, because that id's availability and stability
varies by provider and by code path (see the Outlook adapter note
below) — `Message-ID` is the one identifier guaranteed by the email
standard itself, independent of which API delivered the message.

### Thread detection — layered, provider-native id as one signal among several

The conversation-builder resolves `Conversation.conversation_key` using,
in order of preference:

1. `provider_thread_id`, when the adapter supplied one (Graph
   `conversationId`, Gmail `threadId`) — cheap and reliable when
   available.
2. `In-Reply-To`/`References` header chain walking — universal, works
   for every provider including a future IMAP adapter with no native
   thread concept, since these headers are part of the RFC 5322 message
   itself, not a provider feature.
3. Subject-normalization + participant-set matching — the fallback when
   neither of the above resolves anything (a genuinely fragmented thread,
   or a provider/message missing both signals).

No step in this logic is Outlook- or Graph-specific; it degrades
gracefully per-message based on what a given adapter and a given email
actually supplied, which is exactly why it needs to be layered rather
than assuming one provider's guarantee always holds.

### Provider adapter capability notes — the one real gap, scoped correctly

**General contract:** every `EmailSendCapable` adapter should return a
usable `provider_message_id` and/or guarantee the outbound
`Message-ID` header is capturable, wherever the underlying API allows
it — this is what makes correlating an inbound reply back to an outbound
M5 send possible at all (via `DeliveryQueueItem.id` ↔
`EmailMessage.in_reply_to`/`references` matching against a stored
outbound `Message-ID`). This is a general expectation of any adapter,
not an Outlook-specific requirement.

**Where this is currently unmet:** `OutlookProvider.send()` today always
returns `provider_message_id=None`, because Graph's single-call
`/me/sendMail` endpoint doesn't hand one back. `GmailProvider.send()`
already meets the contract (Gmail's send API returns a real message id).
The fix, already scoped in `future-milestones.md` note 9: switch
`OutlookProvider.send()` to Graph's create-draft-then-send pattern
(`POST /me/messages`, then `POST /me/messages/{id}/send`), which does
return a real id. **This is a change local to the Outlook adapter's
`send()` implementation only** — it does not touch `EmailSendCapable`'s
interface, `DeliverySendOutcome`'s shape, or anything else described in
this document. It is Provider #1's adapter meeting a contract every
adapter is expected to meet, not a special case the core architecture
bends around. A future IMAP send adapter (SMTP-based) would meet the
same contract differently — by minting its own `Message-ID` header
before handing the message to an SMTP relay, since SMTP has no
server-assigned id concept at all — again, entirely adapter-internal.

### Attachments

Metadata-only at sync time (section 2's `Attachment` table), bodies
fetched on-demand through the owning adapter's own attachment-fetch
call — routed generically (`provider_connection_id` → look up the
adapter → call its fetch method with the stored
`provider_attachment_id`), never assumed to be a Graph-shaped call above
that routing layer.

### Failure recovery

`MailboxSyncState.last_sync_status`/`last_sync_detail` record the outcome
of every sync tick, generically, for any provider. Repeated auth
failures (401 from Graph, equivalent from Gmail/IMAP) flip the
underlying `ProviderConnection.status` via the existing, already
provider-neutral `verify_connection`-style status semantics — the same
status concept M5 already uses for send-side auth failures, reused
here, never a parallel or provider-specific status field.

### Rate limits

Every adapter is responsible for respecting its own provider's
throttling contract internally (Graph's `429`/`Retry-After`, Gmail's
quota/backoff model, a future IMAP adapter's own connection-limit
discipline) and translating a rate-limit condition into a shared,
generic retry/backoff signal the mailbox sync worker understands uniformly
— the worker's retry loop does not special-case any one provider's
specific throttling mechanics.

---

## 3a. Provider Capability Matrix

A concrete checklist for whoever implements each adapter — what
`EmailProvider` capabilities a provider needs, what's already true today,
and what's a known, adapter-scoped gap. This table is the practical
companion to section 3: if a row is fully green, adding that provider is
purely additive work behind the existing interfaces; if a row has a gap,
that gap is called out here so it's never rediscovered mid-implementation.

| Capability | `OutlookProvider` (Provider #1) | `GmailProvider` (Provider #2) | `IMAPProvider` (future) | `ExchangeProvider` (future, EWS/on-prem) |
|---|---|---|---|---|
| `EmailConnectionProvider` (OAuth lifecycle) | ✅ Implemented (M5) | ✅ Implemented (M5) | ⚠️ Gap — IMAP is often password/app-password based, not OAuth; needs a non-OAuth `EmailConnectionProvider` variant (see section 8) | ✅ EWS supports OAuth (modern auth) the same shape as Graph |
| `EmailSendCapable` (`send()`) | ✅ Implemented (M5) | ✅ Implemented (M5) | 🔲 Not built — SMTP-based, must mint its own `Message-ID` header (no server-assigned id) | 🔲 Not built — EWS `CreateItem`/`SendItem` |
| Returns a real `provider_message_id` on send | ❌ **Known gap** — Graph's single-call `sendMail` returns none | ✅ Already returns one | 🔲 N/A until built — SMTP has no server id; adapter mints its own `Message-ID` instead | 🔲 Not built — EWS `SendItem` does return an item id |
| Fix required | Switch to create-draft-then-send (`POST /me/messages` → `POST /me/messages/{id}/send`) — scoped, one method, section 3 | None | N/A | N/A |
| `IncrementalSyncCapable` (`fetch_messages_incremental`) | 🔲 Not built — this is M6.2/M6.3 scope, Graph delta query (`@odata.deltaLink`) | 🔲 Not built — future milestone, `users.history.list` (`historyId`) | 🔲 Not built — no native delta; must implement via `UID SEARCH`/`UIDNEXT` tracking encoded into the opaque cursor | 🔲 Not built — EWS `SyncFolderItems` sync-state token maps cleanly onto the cursor contract |
| Native `provider_thread_id` available | ✅ Graph `conversationId` | ✅ Gmail `threadId` | ❌ No native concept — conversation-builder falls back to `In-Reply-To`/`References` + subject/participant matching (section 3, layers 2-3) | ✅ EWS `ConversationId` |
| Dedup basis | `internet_message_id` (`Message-ID` header) — universal, not provider-specific | Same | Same | Same |
| Attachment metadata fetch | 🔲 Not built — Graph `/messages/{id}/attachments` | 🔲 Not built — Gmail `messages.attachments.get` | 🔲 Not built — IMAP `BODYSTRUCTURE`/part fetch | 🔲 Not built — EWS `GetAttachment` |
| Rate-limit handling | Graph `429`/`Retry-After`, adapter-internal | Gmail quota/backoff, adapter-internal | Connection-limit discipline, adapter-internal | EWS throttling policy, adapter-internal |
| `is_configured()` (deployment-level readiness check) | ✅ Implemented (M5) | ✅ Implemented (M5) | 🔲 Not built | 🔲 Not built |

**How to read this table when a new provider is actually built:** every
row that's currently ✅ or a scoped, named gap is evidence the interface
doesn't need to change. Every 🔲 is expected, ordinary adapter
implementation work, not a sign the architecture is incomplete — the
whole point of section 3's interface boundary is that these rows fill in
independently, one adapter at a time, without touching the conversation
model, the AI pipeline, or the CRM logic described in sections 4-6.

---

## 4. AI Reply Intelligence pipeline

**SUPERSEDED for M6.4 — see "Reply Intelligence — as built (M6.4)"
below.** Everything in this section (the `ReplyAnalysis` table,
`PromptVersion`-driven AI classification, `is_analyzed` gating, versioned
re-classification) was the original design at the time this document was
first written. When M6.4 was actually scoped and approved, it was
deliberately simplified: no `ReplyAnalysis` table, no AI call in the
MVP, no `is_analyzed` column, no versioning — `Conversation` gained four
current-state fields instead, and classification is a deterministic
rules engine behind a swappable interface. Left in place below, not
deleted, so the reasoning for the ORIGINAL design is still visible (some
of it — the AI-classification pipeline itself, extraction, `Task`
derivation — is still real, deferred scope for a later milestone, not
abandoned); read it as "the eventual AI-first shape this may grow into,"
not "what M6.4 built."

Entirely provider-agnostic by construction: every input to this pipeline
is `EmailMessage`/`Conversation` data, already normalized by the adapter
layer in section 3. Nothing here reads `EmailMessage.provider`,
`provider_message_id`, or `provider_thread_id` — those columns exist for
correlation and dedup, not for AI logic, which only ever looks at
`body_text`/`body_html`/`subject`/participant data.

Follows the exact pattern M2-M4 already established: `PromptVersion`-
driven (business override → system default resolution, identical to
`_resolve_prompt_version` in `app/outreach/pipeline.py`), a deterministic
stub implementation first (same discipline as
`app/personalization/engine/deterministic_stub.py`), a context object
assembled from existing data, every output frozen with `confidence`/
`reasoning`/`model_used`.

```
Incoming email (synced by mailbox sync worker via IncrementalSyncCapable,
    raw EmailMessage row — provider already normalized away)
    ↓
Conversation builder
    - dedup by internet_message_id
    - thread-match: provider_thread_id → In-Reply-To/References chain →
      subject+participant fallback (section 3)
    - identity resolution: match from_email against ProspectContact.email
      for this company_profile_id; if no match, create the
      ConversationParticipant unresolved (prospect_contact_id = null) -
      never silently create a new Prospect from an unrecognized sender;
      that stays a human-confirmed action
    ↓
AI classification  (intent, sentiment, urgency)
    ↓
Information extraction  (extracted_data JSONB: buyer requests, product,
    quantity, incoterms, destination country, certifications, questions
    asked)
    ↓
ReplyAnalysis row written (confidence, reasoning, model_used,
    prompt_version_id)
    ↓
CRM updates  (section 5)
    ↓
Recommended next action  (Task row, suggested_action derived from intent
    + extracted_data)
```

**Why classification/extraction is one AI call producing one structured
`ReplyAnalysis` row, not several separate calls per field:** matches the
system-prompt-per-channel convention already used for generation
(`_CHANNEL_PROMPT_KEY` in `app/outreach/pipeline.py`) — a single
`reply_analysis` `prompt_key`, one `PromptVersion`, one model call
producing the whole structured object.

### Reply Intelligence — as built (M6.4)

M6.4 was explicitly re-scoped at approval time to a narrower MVP than
this section originally designed. The four changes below were each
argued through and approved before implementation; recorded here as the
real, final decisions, not the earlier draft above.

**1. `Conversation`-only state, no `ReplyAnalysis` table.** Approved
explicitly: *"Conversation should represent the current conversation
state only. We are intentionally not implementing per-message reply
history or a ReplyAnalysis table in M6.4."* `reply_status`/
`last_reply_at`/`last_reply_from`/`needs_human_review` (migration 0012)
live directly on `Conversation` and describe the MOST RECENT inbound
reply only — a later, differently-classified reply overwrites the
earlier one, the same rolling-snapshot semantics `last_message_at`
already has. Trade-off, disclosed and accepted: no per-message
classification history survives. If that is ever needed (e.g. a UI
wanting to show how reply #2 specifically was classified, not just the
conversation's current state), a versioned table is the natural,
additive evolution — not built now.

**2. Shared text extraction lives outside Reply Intelligence.**
`app/core/text_extraction.py`, not `app/reply_intelligence/` — a single
`extract_plain_text(EmailMessage) -> str` helper that the `ReplyClassifier`
interface consumes exclusively (no classifier implementation ever sees
raw HTML or an ORM object). Explicitly designed to be reused, unmodified,
by whatever comes after M6.4 — sentiment analysis, lead scoring,
summarization, search, embeddings — rather than owned by the reply-
classification feature that happened to need it first. Real, disclosed
reason this exists at all: `OutlookProvider` (the only implemented
`IncrementalSyncCapable` provider) never populates `EmailMessage.
body_text` — every inbound message today has to be read from `body_html`,
and this is the one place in the codebase that fact is handled.

**3. Worker progress is NOT tracked against `last_reply_at`.** An
earlier draft of this design compared `EmailMessage.received_at` against
`Conversation.last_reply_at` to decide what needed (re)processing —
rejected explicitly: *"Business timestamps should describe business
events, not worker execution state."* The built design instead does a
full, cheap recompute every tick — `reply_intelligence_worker.py` finds
every `Conversation` with at least one inbound, threaded `EmailMessage`
and reclassifies it from its latest reply, unconditionally, no cursor
column anywhere. Genuinely idempotent (not just "safe to rerun" but "a
rerun with no new data does nothing"), and correct by construction rather
than by cursor bookkeeping. This is a real, disclosed scaling trade-off,
not a free lunch: it rescans every threaded-with-replies `Conversation`
on every tick, forever. Acceptable today because the MVP classifier is a
keyword scan with no external call and effectively free per message; the
natural additive fix if this ever becomes measurably wasteful (a real
AI-classifier's per-call cost/latency, or conversation volume growing
large) is a dedicated cursor table mirroring `MailboxSyncState` — one row
per `Conversation`, holding e.g. `last_processed_message_id` — not built
now because the MVP does not need it.

**4. `needs_human_review` heuristic — NEGATIVE and NEUTRAL only.**
Approved explicitly, overriding an earlier NEUTRAL-only draft: *"Negative
replies are commercially important and should be surfaced for review."*
Final mapping: `POSITIVE` → false, `OUT_OF_OFFICE` → false, `NEGATIVE` →
true, `NEUTRAL` → true.

**`ReplyClassifier` abstraction** (`app/reply_intelligence/classifiers/`):
`ReplyClassificationInput` (plain text + `from_email`/`received_at`
metadata, never an ORM object or HTML) in, `ReplyClassificationResult`
(`reply_status`, `needs_human_review`, and an optional `reason: str |
None` — added specifically so a future AI-backed classifier can populate
a human-readable explanation without ever changing this dataclass's
shape again) out. `RulesReplyClassifier` is the only implementation
today: an ordered, modular rule list (OUT_OF_OFFICE checked first — an
auto-reply's structural signature must never be shadowed by incidental
body wording — then NEGATIVE, then POSITIVE, default NEUTRAL), selected
via `REPLY_CLASSIFIER_BACKEND` through `classifiers/registry.py`, the
same plugin-registry pattern as `EmailConnectionProvider`/
`CredentialStore`. Swapping in OpenAI/Claude/Gemini/a local model later
is a new class + one registry entry — zero change to
`reply_intelligence_worker.py`.

**`app/reply_intelligence/reply_intelligence_worker.py`** — a FOURTH
standalone worker (`reply_intelligence_worker` service in
`docker-compose.yml`, identical single-instance/no-SKIP-LOCKED pattern as
the other three). Reads `EmailMessage` (inbound, already threaded by
Thread Builder) and `Conversation`; writes only the four `Conversation`
columns above. Never writes `EmailMessage`, never touches
`conversation_id` — Thread Builder remains the sole owner of conversation
assignment, structurally unreachable from this worker's code paths, not
just by convention.

Gate: `verify_m6_4.sh` passes — see the M6.4 phased-plan entry below.

---

## 5. CRM integration

**A terminology collision this plan must resolve, not paper over.** The
codebase currently has *two* different, unrelated "pipeline stage"
concepts on *two* different, unrelated models:

- `Company.stage` (`PipelineStage` enum) — lives on the M0 `Company`/
  `Contact`/`Thread`/`Message` model set, which `future-milestones.md`
  note 8 already identifies as "one stale and unwired." Nothing in
  M1-M5 writes to it. `Thread`/`Message` already exist as empty, unused
  tables with `outlook_conversation_id`/`outlook_message_id` columns —
  note the Outlook-specific naming on these dormant, never-used columns
  is itself a small example of exactly the mistake this revision is
  correcting; M6's own tables must not repeat it. **Do not reuse them**;
  see section 9.
- `Prospect.relationship_stage` (`RelationshipStage` enum: cold →
  contacted → engaged → qualified → negotiation) — lives on the live,
  actually-used `Prospect` model. Its own docstring already says "M3
  only ever reads this value; M4-M7 are what advance it as outreach
  happens" — and nothing has advanced it yet at all.

M6 targets `Prospect.relationship_stage` exclusively, provider-agnostic
by construction (the state machine below reacts to `EmailMessage`/
`ReplyAnalysis` facts, never to which provider delivered them).
`Company.stage` is out of scope — flagged as dead-code cleanup, not
touched here.

**State machine** (M6-owned, written nowhere else):
- `cold` → `contacted`: on first successful M5 send (any provider). This
  is technically a pre-existing gap, not new M6 scope — M5 never writes
  this transition either. Recommend M6 close it as a one-line addition
  in `dispatch_service`'s success path.
- `contacted` → `engaged`: on first inbound reply matched to this
  prospect, from any connected mailbox, any provider.
- `engaged` → `qualified`: AI intent = `interested` and a concrete buyer
  request extracted.
- `qualified` → `negotiation`: AI intent = `negotiation`, or a human
  manually advances it.

**`last_contacted_at` / `last_replied_at`.** New columns (section 2).
`last_contacted_at` written by M5 dispatch on successful send;
`last_replied_at` written by M6 on each inbound message, at both
`Prospect` and `ProspectContact` granularity — identical regardless of
which provider the reply arrived through.

**AI score.** Reuses `Prospect.total_score`/`score_breakdown`. M6 adds a
`reply_signal` factor to that same breakdown rather than inventing a
second, competing score field.

**Tasks.** New `Task` table (section 2), surfaced in the frontend
Recommended Actions panel (section 6).

**Activities.** Reuses `ProspectTimelineEvent` exactly as designed — new
`event_type` string values only (`"reply_received"`,
`"ai_reply_classified"`, `"relationship_stage_advanced"`,
`"task_created"`), zero schema change. None of these event types encode
a provider name; `payload` may include `provider` as a data field when
relevant, exactly like every other free-shaped JSONB payload in this
table.

**What M6 does not touch.** `OutreachDraft`, `DeliveryCampaign`,
`DeliveryQueueItem`, `SendingProfile`, `CompanyProfile` — read-only
correlation against these, never a write.

---

## 6. Frontend

Every component below renders from the generic `EmailMessage`/
`Conversation`/`ReplyAnalysis` shape. Provider identity, where shown at
all, is a small badge/label driven by `EmailMessage.provider` (e.g. an
icon + "via Outlook"/"via Gmail") — informational only, never a
different code path per provider.

**Conversation list.** New page, `/businesses/:companyId/conversations`
(business-wide, mirroring `DeliveryCampaigns`'s business-wide list) —
every `Conversation` for the business, sortable/filterable by `status`,
`last_message_at`, unresolved-participant flag, and linked prospect.
Where a business has multiple connected mailboxes across different
providers, this list is unified across all of them — never a
per-provider tab.

**Conversation detail = unified Timeline.** At
`/businesses/:companyId/prospects/:prospectId/conversations/:conversationId`
— chronologically interleaves outbound sends (existing
`DeliveryQueueItem`/`OutreachDraft` history) with inbound `EmailMessage`
rows, regardless of which provider each leg went through.

**AI insights panel**, alongside each inbound message: intent/sentiment/
urgency badges (`StatusBadge`), extracted fields as a compact table,
confidence score, and a collapsible "why" (`reasoning`) — same visual
convention as the existing "Developer details" collapsible on
`ProspectOutreach.tsx`.

**Reply analysis.** Low-confidence analyses visually flagged, with a
manual "re-classify" action creating a new `ReplyAnalysis` row.

**Recommended actions panel.** Open `Task` rows for the prospect, accept/
dismiss actions — same interaction shape already established for
`OutreachDraft` approve/reject.

---

## 7. Background workers

**THREE workers, not two** — a correction over this section's original
"two workers, not one" framing, made explicitly during M6.3's
architecture approval (the open question flagged at the end of M6.2's
own planning round). Thread Builder turned out to be genuinely
independent-cadence work that didn't belong inside either of the other
two — see its own entry below for the reasoning. All three remain
entirely provider-generic: none contains a line of Graph-, Gmail-, or
IMAP-specific code.

**`mailbox sync worker`.** Polls every `ProviderConnection` with read scope
granted, regardless of provider, calling
`fetch_messages_incremental(cursor, max_results)` through the
`IncrementalSyncCapable` interface (section 3). Writes only
`EmailMessage`/`Attachment`-metadata rows (`conversation_id = NULL` on
every row it writes, per section 2's `EmailMessage` lifecycle note) and
updates `MailboxSyncState` — it never writes `Conversation` or
`ConversationParticipant`; that is Thread Builder's job exclusively. No
AI call happens in this worker. `docker-compose.yml` service
`mailbox_sync_worker`, same container shape as the existing `worker`
service.

**`thread_builder_worker` (M6.3, implemented).** Polls `EmailMessage`
rows `WHERE conversation_id IS NULL AND direction = inbound` and runs
`thread_matching.match_conversation()` against each (section 3's
threading algorithm, now built) — attaches to an existing `Conversation`,
creates a new one, or leaves the row for a later pass (bounded, see
`UNTHREADED_RETRY_WINDOW_MINUTES`). Its own poll cadence
(`THREAD_BUILDER_POLL_INTERVAL_SECONDS`, default 20s — faster than
mailbox sync's, since threading is DB-only work with no provider API
calls to pace against) is independent of the sync worker's, which is the
concrete reason this is a third process rather than logic folded into
the sync tick: threading has to be able to retry a "waiting" message on
its own schedule, not only when sync happens to run again. Never calls a
provider adapter, never writes `EmailMessage`/`Attachment`/
`MailboxSyncState` — reads `EmailMessage`, writes `Conversation`/
`ConversationParticipant` only.

**`ai-analysis-worker` (M6.4, not yet built).** Polls `EmailMessage` rows where
`direction = inbound` and `is_analyzed = false` — provider-blind, since
`EmailMessage` is already the normalized shape. Runs the classification/
extraction pipeline (section 4), writes `ReplyAnalysis` + CRM updates +
`Task`, sets `is_analyzed = true`.

**Claiming pattern.** The Delivery worker (M5) already uses
`SELECT ... FOR UPDATE SKIP LOCKED` + `claimed_at` stale-reclaim. **Neither
the mailbox sync worker (M6.2) nor Thread Builder (M6.3) use it** — both
run a plain sequential loop over their own eligible rows within one
process, with no row-level claiming. This is a deliberate simplification
matching every worker's own current deployment reality (a single,
non-horizontally-scaled replica per service in `docker-compose.yml`), not
an oversight — see "Synchronization Cursor Contract — as built" above for
the mailbox sync worker's full reasoning, which Thread Builder repeats
identically. Adding `SKIP LOCKED`-style claiming is additive if either
worker is ever scaled to multiple replicas, not a redesign, but is not
present today.

**Retry strategy.** `attempt_count`/`max_attempts`/`last_error` on
`EmailMessage` (AI-analysis retries) and on `MailboxSyncState` (sync
retries) — same shape as `DeliveryQueueItem`, uniform across providers.

**Failure handling.** Sync failures never drop a message silently:
`MailboxSyncState.last_sync_status = error` is set and logged, and the
cursor is only advanced past messages actually persisted successfully —
identical logic regardless of which adapter produced the failure. AI
failures leave `EmailMessage.is_analyzed = false` and retryable.

---

## 8. Scalability

**Multiple businesses.** Every new table carries `company_profile_id`
(directly or transitively via `Conversation`), the identical scoping
convention every M1-M5 table already uses.

**Multiple mailboxes.** Already supported by construction:
`ProviderConnection` is already 1:many per `CompanyProfile`;
`MailboxSyncState` is 1:1 per connection, so multiple connected mailboxes
— of the same or different providers — sync independently, already.

**Multiple providers — this is the core scalability claim of this
document, not a bullet point.** The entire Provider Integration Layer
(section 3) exists to make this true by construction: a business can have
an Outlook mailbox and a Gmail mailbox connected simultaneously, both
feeding the same `Conversation`/`EmailMessage` tables, both processed by
the identical mailbox sync worker loop and the identical AI pipeline. There
is no code path anywhere above the adapter layer that branches on
provider identity.

**Gmail support later.** Implement `GmailProvider(EmailConnectionProvider,
EmailSendCapable, IncrementalSyncCapable)`: OAuth against Google's
endpoints (send-side already exists in `gmail_provider.py` from M5),
`fetch_messages_incremental` via `users.history.list`. Gmail's send
already returns a real message id, so Gmail has none of the correlation
gap Outlook currently has (section 3) — Provider #2 is, if anything,
easier to correlate than Provider #1. Zero changes anywhere else in this
document's design.

**IMAP support later — a real, disclosed gap, not a trivial add.** IMAP
doesn't fit `EmailConnectionProvider`'s OAuth-shaped contract as cleanly
— IMAP credentials are often username/password or app-specific-password
based, not always OAuth. Being honest about this rather than claiming
it's already accommodated: a future IMAP provider would likely need its
own credential-payload shape parallel to `OAuthTokenPayload` (e.g. an
`EmailConnectionProvider` variant that accepts a stored password instead
of running an OAuth code exchange — a genuine, if small, extension to
that base interface, not something already provided for). Once
connected, though, `IncrementalSyncCapable`'s cursor-based contract and
this document's entire schema (section 2) work unchanged — the adapter
just implements `fetch_messages_incremental` using `UID SEARCH`/
`UIDNEXT` instead of a delta token, encoded into the same opaque
`cursor` string. Worth flagging now as the one place this architecture
isn't 100% free; not solved by this plan.

**Exchange (future).** Same shape as IMAP's story but with EWS's own
sync-state token standing in for the opaque cursor — likely closer to
Graph's model than IMAP's, since Exchange Online *is* Graph underneath;
an on-prem Exchange/EWS adapter would be the more novel case, following
the same `IncrementalSyncCapable` contract regardless.

**Multi-user future.** No user-assignment concept exists on `Task` or
anywhere else in M6 — consistent with the rest of the app, still
single-admin-user throughout.

---

## 9. Migration strategy

**Purely additive.** Six new tables, two new nullable columns on
`Prospect`, two on `ProspectContact`. Zero changes to any existing
table's columns, constraints, or enum values across M0-M5. No migration
file for these tables references Graph, Gmail, or any vendor name in a
table or column name — provider identity is exclusively the `provider`
string column on `EmailMessage` and the pre-existing `provider_key` on
`ProviderConnection`.

**New OAuth scope, opt-in per connection, per provider's own
vocabulary.** `Mail.Read` (Outlook) / `gmail.readonly` (Gmail) requested
only via an explicit Reconnect action on a specific `ProviderConnection`
— existing M5 connections keep working, unaffected, until a user
deliberately opts a given mailbox into Reply Intelligence.

**New capability interface, additive.** `IncrementalSyncCapable` is a
new class in `app/delivery/providers/base.py`, alongside (not replacing)
`MailboxReadCapable`. No existing provider class's declared interface
changes as a result of adding it — `OutlookProvider`/`GmailProvider`
gain a new inherited interface, not a modified one.

**New worker services**, added to `docker-compose.yml` alongside the
existing `worker` service — that service and its image are untouched.

**The one adapter-level change this plan requires**, called out
explicitly: `OutlookProvider.send()` switching from single-call
`sendMail` to create-draft-then-send (section 3's Provider Adapter
Capability Notes). Scoped entirely inside that one method, in that one
adapter file. Because it's a real behavior change to M5's already-
verified send path, it should ship with its own smoke-test coverage
confirming Outlook sends still succeed identically from the caller's
perspective (same `DeliverySendOutcome` shape, just a real
`provider_message_id` instead of `None`) before any M6 feature built on
top of it is considered done. `GmailProvider.send()` requires no
equivalent change.

**Recommend explicit deprecation of the dormant M0 `Thread`/`Message`
tables.** Unused today, wired to the stale `Company` model, and — worth
noting given this revision's theme — already named with Outlook-specific
column names (`outlook_conversation_id`, `outlook_message_id`) that this
plan's provider-neutral `EmailMessage` design deliberately avoids
repeating. Recommend: mark both docstrings superseded-do-not-use in the
same migration that adds M6's own tables, with an actual `DROP TABLE` as
a separate, later cleanup migration once confirmed safe.

---

## 10. Testing strategy

**Unit tests.** Pure-logic pieces get real, executable tests: `Message-ID`
dedup matching, thread-key derivation (all three layers from section 3,
tested independently of any provider — feed the function synthetic
`RawEmailMessage` structs, not real Graph/Gmail payloads), the
`relationship_stage` state-machine transition function, and the
extraction-to-`Task`-suggestion mapping. Because the conversation-builder
and AI pipeline consume only the normalized `RawEmailMessage`/
`EmailMessage` shape, these tests require zero provider-specific mocking
— a single synthetic-message fixture set exercises the entire pipeline
regardless of which real provider would have produced it.

**Provider adapter tests, isolated per adapter.** `OutlookProvider`'s
`fetch_messages_incremental`/`send()` and `GmailProvider`'s equivalents
are tested separately, each responsible only for correctly translating
its own vendor's API shape into `RawEmailMessage`/
`DeliverySendOutcome` — the same isolation principle already used for
`OutlookProvider`/`GmailProvider`'s existing M5 send-path tests.

**Deterministic AI stub first**, exact precedent of
`deterministic_stub.py`: a rule-based classifier standing in for a real
LLM, so the full pipeline is provably correct end-to-end before a real
model is wired in — and, because the pipeline is provider-blind, this
stub needs no provider-specific test data at all.

**Integration tests.** A `verify_layer*.sh`-style script covering:
Reconnect with read scope (both providers, once Gmail exists), sync
worker persisting messages from a stubbed/mocked adapter response,
AI-analysis worker producing `ReplyAnalysis`/`Task`/CRM updates, and a
full synthetic-inbound-message-to-`relationship_stage`-transition walk —
run once against a stubbed Outlook adapter and, once Gmail ships, the
identical test run again against a stubbed Gmail adapter with no changes
to the test's assertions about conversation/AI/CRM behavior — that
parity is itself the acceptance test for "provider-agnostic."

**End-to-end / real-provider verification.** Same disclosed, permanent
boundary M5 already documented in `m5-production-readiness.md`: real
inbox sync against a real mailbox cannot be automated in this sandbox
(no live tenant/account access here) and must be manually verified by
you — for Outlook first, since it's Provider #1, and again for Gmail
once Provider #2 ships. This should be the final gate before tagging
`M6-Stable`, mirroring the `M5-Stable` gate.

---

## 11. Risks

- **Persistent mailbox content is a new privacy/security surface that
  didn't exist before M6**, independent of provider. Mitigations already
  designed in: bounded first-sync window, attachment bodies never
  stored, opt-in per connection. Not yet designed, flagged as a gap this
  plan does not close: a disconnect-and-purge action that actually
  deletes `Conversation`/`EmailMessage` rows for a connection. Recommend
  this be a required part of M6 implementation given the privacy stakes.
- **The Outlook adapter's `send()` change is a real-send-path change to
  already-verified, production-tagged M5 code.** Low technical risk
  (scoped to one method in one adapter file), but nonzero — must be
  re-verified against a real Outlook send before M6 ships.
- **Identity resolution will be imperfect**, regardless of provider.
  Email-address matching against `ProspectContact.email` will miss
  aliases, personal addresses, and forwarded threads. Unresolved
  participants are surfaced, not silently dropped or auto-matched.
- **AI misclassification risk on `relationship_stage` transitions.**
  Because this state machine is now automatically *written*, a wrong AI
  intent classification could incorrectly advance a prospect's stage.
  Mitigated by confidence surfacing and forward-only automatic
  transitions, but worth revisiting after real usage data exists.
- **New architectural risk introduced by this revision, named
  honestly:** an abstraction built for providers that don't exist yet
  (Gmail's adapter isn't written, IMAP's isn't even fully designed) can
  guess wrong about what the interface needs. `IncrementalSyncCapable`
  is designed against Graph's delta model and Gmail's `history.list`
  model, both of which are genuinely cursor-shaped — reasonable
  confidence there. IMAP's UID-based model is a real stretch fit,
  flagged in section 8 rather than glossed over; it may turn out to need
  a small interface adjustment when actually built, which is normal and
  fine as long as it stays additive.

---

## 12. Architectural trade-offs

- **Two workers instead of one.** Costs one more container/process;
  buys independent scaling and failure isolation between cheap sync and
  expensive AI calls — same trade-off M5 already made, judged worth
  repeating.
- **A new `IncrementalSyncCapable` interface instead of widening
  `MailboxReadCapable`'s existing signature.** Costs one more capability
  class to reason about. Buys: zero disruption to M5's already-declared
  `MailboxReadCapable` contract (note 9's manual-brief use case, if ever
  built, still has a clean, unmodified home), and a cursor-shaped
  contract that's honest about being a different access pattern from a
  one-shot time-windowed read rather than overloading one method to mean
  two things.
- **JSONB `extracted_data` instead of typed columns per extracted
  field.** Costs some query-ability. Buys schema stability as the AI's
  extraction vocabulary evolves — identical trade-off already made for
  `OutreachDraft.ai_generated_content`/`Prospect.score_breakdown`.
- **Storing message bodies at all** is the central trade-off of this
  whole document — see Decision Point 0. Provider-agnosticism doesn't
  change this trade-off's shape, only ensures it's paid once, uniformly,
  not once per provider with subtly different guarantees each time.

---

## 13. Alternative designs considered

**Alternative A — ship note 9's original design first.** Build only the
manual, click-triggered, ephemeral Mailbox Brief, defer the persistent
architecture to a later M6.5. Still fully provider-agnostic under this
revision's design either way — `MailboxReadCapable` alone, no
`IncrementalSyncCapable`, no persistent tables. Pro: zero new privacy
surface, much smaller implementation. Con: doesn't deliver a timeline,
reply-analysis history, or automatic CRM updates. Recorded as a
legitimate lower-risk first slice, not the primary recommendation.

**Alternative B — webhook-first sync.** Rejected for v1 per section 3:
real infrastructure and testability gap this sandbox can't close;
recorded as a documented future upgrade, itself provider-generic (each
provider's webhook mechanism would feed the same ingest path a poll tick
uses today).

**Alternative C — reuse the dormant `Thread`/`Message` tables.**
Rejected per section 9: wrong parent entity, and — relevant to this
revision specifically — those tables' own column names
(`outlook_conversation_id`, `outlook_message_id`) already bake in the
provider-centric mistake this document exists to avoid repeating.

**Alternative D — typed columns instead of JSONB for extraction
output.** Rejected per section 12: schema churn, inconsistent with the
JSONB convention already used for every other AI-shaped output.

**Alternative E — a single `MailboxReadCapable.fetch_recent_messages`
signature doing double duty for both one-shot briefs and incremental
sync**, e.g. by overloading `since` to sometimes mean "opaque cursor."
Rejected: conflates two different access patterns into one method
signature with type-unsafe dual meaning, exactly the kind of interface
smell this revision is trying to eliminate elsewhere. A second, explicit
capability interface (`IncrementalSyncCapable`) is more code but a
cleaner contract.

---

## 14. Phased Implementation Plan (M6.1–M6.5, plus one deferred, unscheduled phase)

**Note on numbering (post-M6.5 rescoping):** this section originally ran
M6.1 through M6.6. M6.5 was rescoped at approval time to build
Conversation UI (this document's original M6.6 scope) instead of CRM
updates & recommended actions (this document's original M6.5 scope) —
see M6.5's own entry below for the full reasoning. The token "M6.6" is
retired, not reused for a second meaning; CRM updates & recommended
actions is tracked below as deferred and unscheduled.

M6 will be implemented in the same layer-by-layer, build-test-verify
discipline M5 was built under — each phase ships something concrete and
independently verifiable, gated by explicit approval before the next
phase starts, exactly like M5's Layer 1-7 sequence. No phase begins until
the previous one's verification is confirmed.

**M6.1 — Conversation & EmailMessage schema + migrations.**
Scope: the six new tables (`Conversation`, `EmailMessage`,
`ConversationParticipant`, `Attachment`, `ReplyAnalysis`,
`MailboxSyncState`, `Task` — section 2), the additive `last_contacted_at`/
`last_replied_at` columns on `Prospect`/`ProspectContact`, and the
superseded-do-not-use docstring markers on the dormant `Thread`/
`Message` models (section 9). No business logic, no worker, no routes —
schema only, plus Pydantic schemas for the new tables.
Gate: migration applies cleanly on top of the current `M5-Stable`
schema, `py_compile`/model-import sanity check (mirroring every prior
milestone's Layer 1 verification), and a written confirmation that no
existing table's columns/constraints changed.

**M6.2 — Provider sync engine (Outlook first, provider-agnostic
architecture). IMPLEMENTED, pending your verification.**
Scope, as actually approved and built: `IncrementalSyncCapable` added to
`app/delivery/providers/base.py`; `OutlookProvider` implements it (Graph
delta query — see "Synchronization Cursor Contract — as built" above for
the precise mechanism); `MailboxSyncState`/`Attachment` models + migration
0010 (also making `email_messages.conversation_id` nullable, framed
strictly as a temporary processing state per your explicit instruction);
the `mailbox_sync_worker` service, writing raw `EmailMessage`/
`Attachment`-metadata rows only (`conversation_id = NULL`) with no AI or
CRM logic. **Reassigned out of M6.2, during its own architecture
approval round:** the `OutlookProvider.send()` create-draft-then-send fix
this entry originally scoped here — it belongs with M6.3's outbound
correlation work instead (send() needs to start returning a real
`provider_message_id` specifically so M6.3 can match an outbound send
back to an inbound reply; M6.2 itself is inbound-only and has no use for
that fix). `GmailProvider`/`IMAPProvider` are **not** implemented in this
phase — the Provider Capability Matrix (3a) is the checklist for when
they are, later, as their own follow-on work.
**Known gap, disclosed at implementation time:** M6.2's approved scope
did not include a Reconnect-with-expanded-scopes route/UI, so no real
`ProviderConnection` today can actually be granted `Mail.Read` — the sync
worker's eligibility check (`has_read_scope`) is correct and will find
zero eligible connections until that small follow-up exists or a
connection is manually re-scoped for testing.
Gate: a real Outlook mailbox with a real inbound test email is
synced into `EmailMessage` correctly (verified by you, same disclosed
real-provider boundary as M5 — requires the Mail.Read gap above to be
worked around first); `MailboxSyncState.cursor` correctly resumes
across worker restarts; no regression in existing M5 Outlook send smoke
test steps; `verify_m6_2.sh` passes.

**M6.3 — Conversation threading & reply correlation. IMPLEMENTED,
pending your verification.**
Scope, as actually approved and built: `app/reply_intelligence/
thread_matching.py` (the six-step matching algorithm — provider thread
ID as a provisional first pass, In-Reply-To/References as the
authoritative Message-ID chain that always wins on conflict, a bounded
30-minute "wait for a still-syncing parent" retry, and a subject
fallback strengthened at approval time to require ALL of normalized
subject + participant overlap + `Conversation.status == OPEN`) and
`app/reply_intelligence/thread_builder.py` (a THIRD standalone worker —
approved explicitly in preference to folding this into the mailbox sync
worker, for independent retry/monitoring/failure isolation — the
`thread_builder_worker` service in `docker-compose.yml`). Populates
`Conversation`/`ConversationParticipant`, assigning `EmailMessage.
conversation_id` for every inbound row M6.2 left `NULL` — `WHERE
conversation_id IS NULL AND direction = inbound` is this phase's entire
work queue.

Outbound correlation is NOT part of Thread Builder itself — `dispatch_
service.py` (M5) now assigns `conversation_id` synchronously, at send
time, via `app/reply_intelligence/conversation_resolver.py`
(`get_or_create_conversation_for_outbound`/`upsert_participant`, shared
with Thread Builder so the two writers can't drift on what "the right
Conversation" means), isolated in its own SAVEPOINT so a bookkeeping bug
can never undo an already-successful send. The
`OutlookProvider.send()` create-draft-then-send fix landed here as
planned — its real payoff turned out to be reading back Graph's own
server-generated `internetMessageId` (what a reply's In-Reply-To will
actually reference), not just obtaining a `provider_message_id`.
`GmailProvider.send()` got the complementary fix: it mints and sets its
own `Message-ID` header directly, since it already authors the raw MIME
payload and doesn't have Graph's uncertainty.

**Disclosed, additive correction found during implementation, not part
of the original M6.1/M6.2 field list:** `EmailMessage.to_recipients`/
`cc_recipients` (migration 0011, nullable JSONB) — without them,
`ConversationParticipant` had no way to learn about CC'd stakeholders on
inbound messages; `from_email`/`from_name` only ever captured the
sender. Migration 0011 also adds a plain (non-unique) index on
`internet_message_id` (approved M6.3 adjustment) — required because
Message-ID matching searches across every connection a company owns, not
just one, which the connection-scoped partial unique index from
migration 0009 can't serve efficiently.

Gate: a real outbound M5 send followed by a real inbound reply
correctly resolves into one `Conversation`, correctly links back to the
originating `DeliveryQueueItem`, and an unrecognized sender correctly
produces an unresolved `ConversationParticipant` rather than a silent
drop or a wrongly-invented `Prospect`; `verify_m6_3.sh` passes, including
its full M6.1/M6.2 regression pass (M6.3 touched shared provider/model
files).

**M6.4 — Reply Intelligence (deterministic classification).
IMPLEMENTED, pending your verification.**
Scope, as actually approved and built — a deliberate, explicitly-approved
simplification of this section's original scope (see "Reply Intelligence
— as built" below for the full reasoning): NOT a `ReplyAnalysis` table,
NOT `PromptVersion`, NOT `is_analyzed`, NOT versioned re-classification.
`Conversation` gained four fields directly
(`reply_status`/`last_reply_at`/`last_reply_from`/`needs_human_review`,
migration 0012) representing current state only — the most recent
inbound reply, not a history. A new `app/core/text_extraction.py`
(deliberately outside `app/reply_intelligence` — a shared, reusable
`EmailMessage -> plain text` helper for this and every future AI-facing
feature) feeds a provider-agnostic `ReplyClassifier` interface
(`app/reply_intelligence/classifiers/base.py`), implemented today by one
deterministic, keyword-based `RulesReplyClassifier` (four categories:
POSITIVE/NEGATIVE/NEUTRAL/OUT_OF_OFFICE), selected via a registry
(`REPLY_CLASSIFIER_BACKEND`, mirroring every other provider-registry
pattern in this codebase) so an OpenAI/Claude/Gemini/local-model
classifier can be added later as a new class + one registry entry, never
a worker change. `app/reply_intelligence/reply_intelligence_worker.py` —
a FOURTH standalone worker (`reply_intelligence_worker` service in
`docker-compose.yml`) — does a full recompute every tick (every
Conversation with an inbound, threaded message is reclassified from its
latest reply) rather than tracking a cursor against any business field;
see the "as built" section below for why. Never writes `EmailMessage`,
never touches `conversation_id` — Thread Builder remains the sole owner
of conversation assignment, untouched by this milestone.
Gate: `verify_m6_4.sh` passes — the rules classifier produces correct
classifications for every documented example plus the OOO-precedence and
NEGATIVE-over-POSITIVE priority-order cases; the worker correctly ignores
outbound-only conversations and never-threaded messages; a rerun with no
new data is a true no-op; a newer reply correctly overwrites an older
classification on the same Conversation.

**M6.5 — Conversation UI. RESCOPED at approval time, IMPLEMENTED.**
This phase's original scope (below, "M6.5 — CRM updates & recommended
actions") was explicitly deferred at approval time in favor of building
the Conversation UI first — the reasoning: the M7 Workflow Engine
extension arc (Discovery/Research/Personalization/Outreach, tracked as
M8.13-M8.15) had just completed, and the CRM-updates milestone's own
`Task`/Recommended Actions panel has no UI to surface it in yet anyway,
so building the UI against the already-real M6.1-M6.4 data first (rather
than building more backend state with still no page to show it on) was
judged the better sequencing. This is a **rename, not a cancellation** —
the original "M6.5 — CRM updates & recommended actions" scope is real,
deferred work, now tracked below as a **future, unscheduled milestone**
(no number reserved for it until it's actually next).

Scope, as actually built: `GET /company-profiles/{id}/conversations`
(business-wide list) and `GET .../conversations/{conversation_id}`
(detail: participants + the unified message timeline) — read-only,
zero new tables, zero new write path; every field exposed was already
written by M6.1-M6.4. `EmailMessage` already carries both inbound and
outbound legs of a conversation (`direction` distinguishes them), so no
separate interleaving of `DeliveryQueueItem`/`OutreachDraft` history is
needed for the "unified Timeline" this document's section 6 describes —
confirmed during implementation, not assumed. The frontend
(`Conversations.tsx`) follows Reports.tsx's (M8.9) List -> Detail expand
pattern rather than a new routed sub-page, lives at the pre-existing
global `/conversations` route (Analytics.tsx/Reports.tsx's established
Intelligence-zone convention: global route, scoped internally via the
active company context), and shows an AI insights section limited to
the four real M6.4 fields (`reply_status`/`needs_human_review`/
`last_reply_at`/`last_reply_from`). **No Recommended Actions / Task
panel** — no `Task` table exists yet; showing one here would be
fabricating state, which this project does not do.
Gate: `py_compile` clean backend, `tsc -b --force` clean frontend. Full
real-Outlook end-to-end verification (a real sent email, a real reply,
a real classification, visible correctly in this UI) remains part of
the single, later, comprehensive verification phase this project's
standing discipline already defers all real-Postgres/browser
verification to — not a per-milestone gate here.

**M6.6 (renumbered from this document's original M6.6) — Wire
Personalization/Outreach into the M7 Workflow Engine. COMPLETED under a
different name.** What this document originally called "M6.6" (below)
was Conversation UI + end-to-end verification; that work is now M6.5
above. The *number* M6.6 itself was never actually used for anything —
it is retired from this document's own numbering rather than reassigned
a second time, to avoid a third meaning for the same token. See the
project's roadmap-renumbering record (M8.13/M8.14/M8.15) for the
unrelated milestones that actually shipped in this window.

**Deferred, unscheduled — CRM updates & recommended actions (this
document's original M6.5 scope).**
Scope, unchanged from the original plan: the `relationship_stage` state
machine (section 5), including closing the pre-existing
`cold`→`contacted`-on-send gap in `dispatch_service`;
`last_contacted_at`/`last_replied_at` writes; `ProspectTimelineEvent`
entries; the `reply_signal` scoring factor; the `Task` table writes and
suggested-action derivation.
Gate (unchanged): a full synthetic walk — send, reply, classify —
correctly advances `relationship_stage` through each transition in
order, appends the expected timeline events, and produces a sensible
`Task`; confirms no write ever touches `OutreachDraft`/
`DeliveryCampaign`/`DeliveryQueueItem`/`SendingProfile`/`CompanyProfile`
(the boundary section 1 and 5 commit to). Once this lands, the
Conversation UI's Recommended Actions panel (section 6) becomes an
additive follow-up to `Conversations.tsx`, not a redesign of it.

**What's deliberately excluded from this phase sequence, by design.**
`GmailProvider`/`IMAPProvider`/`ExchangeProvider` implementations are not
phases of M6 itself — per the Provider Capability Matrix (3a), they are
independent, later, additive work that becomes possible *because* M6
was built against the interface rather than against Outlook directly.
Each would be its own short, self-contained milestone (build the
adapter, verify against a real account, done) once M6.1-M6.5 and the
deferred CRM-updates milestone land, never a reason to reopen any of
the phases above.

---

## Why this design is the recommended long-term direction

It extends every pattern this project has already proven rather than
inventing new ones: capability-based providers (already built for
exactly this in M5, now extended with one clean additional interface),
`PromptVersion`-driven AI with a deterministic stub (M2-M4), append-only
evidence/event tables, frozen-content-at-the-point-of-use discipline,
and the "AI recommends, human decides" boundary held everywhere else in
this system. The provider-agnosticism requirement in this revision isn't
bolted on after the fact — it's enforced structurally: every table in
section 2 stores provider identity as a data column, never a schema
concept; every piece of logic in sections 4-8 operates on the normalized
`EmailMessage`/`RawEmailMessage` shape and would behave identically if
every row's `provider` column read `"gmail"` instead of `"outlook"`
tomorrow. The one place this document departs from prior guidance
(Decision Point 0) is named and justified rather than smoothed over, and
the one required Outlook-adapter change (send-path correlation) is
scoped to a single method with no interface impact. Nothing here
requires redesigning M0-M5; it is additive in the same sense every
milestone since M1 has been — and Gmail, when it arrives, should cost
one new adapter file, not a rewrite of this one.

---

**This document is a proposal. No code has been written. Decision Point 0
is resolved (persistent model adopted). Awaiting explicit approval to
begin implementation, phase by phase per section 14, starting with
M6.1.**
