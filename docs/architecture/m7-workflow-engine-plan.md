# M7.1 — Workflow Engine: Architecture Proposal

**Status: ARCHITECTURE APPROVED. Implementation not yet authorized.**
No code, no migrations, nothing in this document has been built. The
design itself (this document) is approved as of the third review round;
what has not yet happened is the separate implementation-planning pass
(scoping the pilot workflow, the concrete file/module layout, migration
sequencing) that this project has required before writing code at every
prior milestone — M7.1 is not an exception. Same discipline as
`m6-reply-intelligence-plan.md`'s own Decision Point 0.

**Revision history, folded into the document below (not tracked as a
separate diff — this is the current, complete, approved design):**

1. First review: overall direction approved, with two required additions
   — explicit `WorkflowDefinition` versioning semantics and
   definition-level governance metadata (both in section 3).
2. Second review: those two additions approved; one further requirement
   — an explicit, consolidated Workflow Definition Compatibility Policy
   (section 3, its own subsection) stating the immutability/pinning/
   no-migration rules as a direct governance contract rather than
   leaving them implied across the versioning discussion.
3. Third review: **architecture approved in full.** Every recommendation
   from the original draft (two dedicated workers, Postgres transactional
   outbox, opaque `subject_type`/`subject_id`, unified wait-for-event
   mechanism, platform-authored-only v1, single-pilot-workflow-first,
   immutable versioning, `DRAFT`/`ACTIVE`/`DEPRECATED` lifecycle) was
   explicitly re-affirmed, unchanged, across all three rounds.

## 0. Why this exists, and the trap to avoid

Every module built so far (M1 Discovery, M2 Research, M3 Personalization,
M4 Outreach, M5 Delivery, M6.1–M6.4 Reply Intelligence) independently
invented the same shape at least once: a `*JobStatus` enum
(`DiscoveryJobStatus`, `ResearchJobStatus`, `PersonalizationJobStatus`,
`OutreachJobStatus` — all `PENDING`/`RUNNING`/`COMPLETED`/`FAILED`/
`CANCELLED`, near-identical field for field), a Job/Run pair, and either
a human/API call or a worker's own polling query to decide "what runs
next." Nothing today automatically chains "Prospect qualified → generate
a draft" or "reply classified NEGATIVE → do something about it" — that
handoff is either a manual API call or doesn't exist yet. The Workflow
Engine is the generalization of that five-times-repeated pattern into
one reusable orchestration primitive, and the mechanism that finally
makes cross-module handoffs declarative instead of hand-wired.

**The trap:** building a fully generic engine against all six existing
modules at once, before a single real workflow has run end-to-end, risks
exactly the kind of premature, speculative abstraction this project has
consistently avoided (see `future-milestones.md`'s own repeated
walk-backs of anticipatory schema). This document designs the whole
engine because that's what was asked for, but Recommendation 1 in
section 17 is explicit: implement it against **one pilot workflow**
first, not all six modules simultaneously.

---

## 1. High-level architecture and module boundaries

The Workflow Engine is a new, domain-agnostic coordination layer that
sits **above** every existing module, not inside any of them. Today,
cross-module handoffs happen either manually (a human/API call triggers
the next stage) or, in one case (M6.3), via direct code — `dispatch_
service.py` calling `conversation_resolver.py` synchronously. That
in-module call stays exactly as it is (it's *within* Delivery's own
domain boundary, not a cross-module orchestration concern). What changes
is any *cross-module* handoff: those become event-driven through the
engine instead of ad hoc.

```
 ┌───────────────────────────────────────────────────────────────────┐
 │                         Domain Modules                              │
 │   Discovery   Research   Personalization   Outreach   Delivery      │
 │        Mailbox Sync   Thread Builder   Reply Intelligence           │
 │                                                                       │
 │   Each module, unchanged internally, gains two thin, additive       │
 │   integration points:                                                │
 │     - publishes domain Events at its own natural completion points  │
 │     - registers domain Actions the engine can invoke                │
 └───────────────────────────┬───────────────────────────┬─────────────┘
                              │ publish                    │ invoke
                              ▼                             │
                    ┌───────────────────┐                   │
                    │     Event Bus       │                   │
                    │ (Postgres `events`  │                   │
                    │  table, section 2)  │                   │
                    └─────────┬───────────┘                   │
                              │ dispatch                       │
                              ▼                                │
                    ┌───────────────────────┐                  │
                    │   Workflow Engine Core  │                  │
                    │  - Workflow Definitions │                  │
                    │  - Workflow Instances    │◄─────────────────┘
                    │  - State Machine (sec 4) │   Action Registry
                    │  - Action dispatch        │   (section 6)
                    └───────────────────────────┘
```

**Module boundary, stated as a contract:** the engine never imports
`app.models.email_message`, never imports `app.outreach`, never imports
anything from any domain package. Its only vocabulary is *Events*
(opaque `event_type` strings + opaque JSONB payload), *Workflows*
(definitions + instances + steps), *Actions* (opaque `action_key`
strings + opaque JSONB input/output), and *state transitions*. Domain
modules own 100% of the meaning behind those opaque strings/payloads.
This is enforced structurally, not just by convention: the engine's own
package (`app/workflow_engine/`, proposed) has zero import dependency on
any of `app.discovery`/`app.research`/`app.personalization`/`app.
outreach`/`app.delivery`/`app.reply_intelligence` — dependencies only
ever point the other way (a domain module imports the engine's
`publish_event()`/`register_action()` helpers, never the reverse).

**One necessary exception, called out explicitly:** the engine *does*
need to understand `company_profile_id` as a generic tenant-scope
identifier, for isolation (section 12). This is not domain knowledge —
it's the same kind of generic "tenant" concept any multi-tenant queue
product needs without knowing what a tenant's business does — but it's
worth stating plainly rather than pretending the engine is *completely*
knowledge-free. Similarly, `subject_type`/`subject_id` (section 2) are
opaque *correlation* keys the engine stores and indexes but never
interprets.

---

## 2. Event system

### Event model

Conceptually, one `Event` carries:

- `event_id` — unique identifier.
- `event_type` — a namespaced string the domain owns entirely (e.g.
  `"prospect.qualified"`, `"outreach.draft.approved"`,
  `"delivery.sent"`, `"conversation.reply.classified"`). Same "plain
  string, not an enum — adding one is a code change, never a migration"
  convention already used for `provider_key`/`channel_key` everywhere in
  this codebase. The engine treats this as an opaque matching key only.
- `occurred_at` + `sequence_no` — see Ordering below.
- `company_profile_id` — tenant scope (see section 1's exception).
- `subject_type` / `subject_id` — an opaque "what business entity is
  this about" pair (e.g. `subject_type="prospect"`,
  `subject_id=<uuid>`). The engine never interprets `subject_type`
  strings; they exist purely so workflow instances and events can be
  correlated and so an operator/future UI can ask "show me everything
  that happened to this entity" without the engine knowing what "this
  entity" means.
- `payload` — opaque JSONB, meaningful only to the domain module that
  published it and the Action handlers that read it.
- `source` — which module published it (for debugging/explainability,
  not for routing).
- `correlation_id` — ties a whole chain of related events/workflow
  activity together across module boundaries (e.g. one outbound send's
  entire life: drafted → approved → sent → replied-to → classified all
  share one `correlation_id`).
- `causation_id` — the specific event or action invocation that directly
  produced this event, one level up (distinct from `correlation_id`,
  which spans the whole chain) — this is what makes the system
  genuinely **explainable**: given any event, you can walk `causation_id`
  backwards to the exact thing that caused it, and `correlation_id`
  sideways to everything else in the same business process.
- `schema_version` — an integer, so a payload shape can evolve without
  breaking older, already-stored events.

### Event lifecycle

```
   published (written to the events table)
        │
        ▼
   dispatched (visible to the Event Dispatcher worker's poll query)
        │
        ▼
   matched against:
      - active WorkflowDefinitions' trigger clauses  → may START new instances
      - WAITING WorkflowInstances' subscriptions       → may RESUME instances
        │
        ▼
   consumption recorded (EventConsumption row per instance touched,
   see section 7 — this is what makes re-processing the same event safe)
        │
        ▼
   processed (no further action; the row is retained permanently as an
   append-only audit record, never deleted — same discipline as
   DeliveryEvent/OutreachEdit/ProspectTimelineEvent elsewhere in this
   codebase)
```

An event that matches **zero** definitions/instances is not an error —
most events won't be relevant to any currently-active workflow, and
that's expected, not a failure.

### Event publishing

**Transactional outbox, not a message broker.** A domain module writes
its own business row (e.g. `Conversation.reply_status = NEGATIVE`) and
an `Event` row in the *same* database transaction, via a small shared
`publish_event(db, ...)` helper. This avoids the classic dual-write
inconsistency (business change committed but event lost, or vice versa)
without needing a separate broker: in a single-Postgres deployment, the
"outbox" and "the log the engine reads" can be the same table.

This is a deliberate, explicit choice against Kafka/RabbitMQ/SQS for v1
— see section 13 (Alternatives) for the full reasoning. Short version:
every worker in this project (Delivery, Mailbox Sync, Thread Builder,
Reply Intelligence) already runs single-instance, Postgres-only, no
external broker, no `SKIP LOCKED` even — introducing a message broker
here would be the single largest new infrastructure dependency in the
project's history, for a scale this product does not operate at today.

### Event consumption

Two independent worker responsibilities read the `events` table (see
section 5 for why these are two workers, not one):

1. **New-instance matching** — for the `WorkflowDefinition` whose
   `status = ACTIVE` (at most one per `key`, section 3) and whose
   trigger clause names this `event_type` (optionally filtered further
   against `payload`/`subject_type`), start a new `WorkflowInstance`,
   pinned to that exact version.
2. **Resume matching** — for every `WorkflowInstance` currently
   `WAITING` on a subscription that names this `event_type` (optionally
   filtered against `subject_id`/`correlation_id` so the *right* waiting
   instance resumes, not every instance waiting on that event type
   generically), transition it back to `RUNNING`.

### Event storage

One `events` table (see section 7), Postgres, JSONB payload,
append-only. Indexed on `(company_profile_id, event_type, occurred_at)`
for the dispatcher's own poll query, and on `correlation_id` for
explainability lookups. No hard delete — retention/archiving is a real,
disclosed future concern (section 11), not solved in v1.

### Ordering

Two different ordering guarantees, deliberately kept separate:

- **Global ordering across unrelated events does not matter** and is not
  guaranteed — same principle as a partitioned broker, without needing
  actual partitions. Two events about two different prospects have no
  ordering relationship the engine needs to preserve.
- **Ordering *within* one workflow instance matters completely** — a
  `WorkflowInstance` is only ever processed by one worker "unit of work"
  at a time (see Concurrency, section 5), so events resuming the *same*
  instance are inherently serialized by the instance's own claim, not by
  a broker guarantee. A monotonic `sequence_no` (not wall-clock
  `occurred_at`, which can tie within the same transaction) is the true
  total order the dispatcher polls by.

### Idempotency

Every `(event_id, workflow_instance_id)` pairing that the dispatcher acts
on is recorded once in `EventConsumption` under a unique constraint —
reprocessing the same event against the same instance is a guaranteed
no-op. This mirrors a pattern already proven at scale in this codebase:
the partial-unique-index dedup on `internet_message_id` (M6.1) and every
M6 worker's "fresh session per item, commit per item, safe to rerun"
discipline.

Event-level idempotency is *not* the same as **Action**-level
idempotency (i.e. "don't send the same email twice"). The engine can
guarantee it won't process the same event against the same instance
twice — it cannot itself guarantee an Action's real-world side effect
only happens once, because it doesn't know what the side effect *is*.
The engine's contribution is a stable `idempotency_key` per step
invocation attempt, which Action handlers *may* use to dedupe on their
own side (their responsibility, matching the "engine doesn't know what
an email is" boundary exactly).

---

## 3. Workflow model

### Workflow Definitions

Declarative, not code. A `WorkflowDefinition` is versioned and immutable
once any instance references it — identical discipline to
`OutreachDraft`/`PersonalizationSnapshot`'s "frozen once produced, a new
version is a new row" convention already established in this codebase.
Conceptually: a `key` (e.g. `"standard_outbound_sequence"`) that names
*what workflow this is* across all its versions, a `version` (integer,
monotonically increasing per `key` — e.g. `Outreach Workflow v1, v2,
v3`, each its own immutable row), a **trigger clause** (which
`event_type`(s) start a new instance, plus an optional filter expression
against payload/subject), and a **step graph** — each step names an
`action_key` plus transition rules ("on `SUCCESS` go to step B; on
`FAILURE` go to step C; on `TIMEOUT` go to step D").

**Versioning — required, and a hard invariant, not just a convenience.**
Every `WorkflowDefinition` row is one immutable `(key, version)` pair —
publishing a change is *always* a new row with `version + 1`, never an
edit to an existing version's step graph or trigger clause (this is what
"immutable once any instance references it" means in practice: nothing
stops a still-`DRAFT`, never-activated version from being edited in
place, but the instant it's activated, it's frozen forever, exactly like
`OutreachDraft`). Two rules follow directly, and both are non-negotiable
engine invariants, not policy the engine merely defaults to:

- **A running `WorkflowInstance` stays on the exact version it was
  created against, permanently.** The instance row pins both
  `workflow_definition_id` *and* the specific `version` number at
  creation (already stated in the Workflow Instances subsection below);
  nothing about that pin ever changes for the life of the instance, even
  if the same `key` later gets a v4, v5, v6. The engine has **no**
  mechanism — automatic or manual — that moves a running instance from
  the version it started on to a different one. If a business needs an
  in-flight instance to behave like the new version, the only path is
  operator-driven: cancel the old instance and let a new trigger event
  start a fresh one against the new version. That is a deliberate
  product decision left to a human, never an engine behavior.
- **A newly triggered instance always resolves to whichever version of
  that `key` currently holds `ACTIVE` status** (see Metadata below) —
  never "the highest version number" as a raw heuristic, and never a
  version pinned by anything other than its own `status` field. This
  keeps "which version is currently live" a single, explicit, queryable
  fact (`status = ACTIVE`) rather than something inferred from a MAX()
  over version numbers, which would silently do the wrong thing the
  moment a `DRAFT` version with a higher number exists but isn't ready
  yet.

**Platform-global vs. business-authored**, an explicit open decision
(flagged again in section 17): `company_profile_id` on a definition is
nullable. `NULL` = platform-authored, applies to every business.
Non-null = one specific business's own custom sequence. This mirrors the
"system default vs. business override" resolution pattern already
established for `PromptVersion` (`_resolve_prompt_version` in `app.
outreach.pipeline`) — not a new idea, the same one applied to workflows.
**Recommendation: defer business-authored definitions past v1** (see
section 17) — ship platform-authored only first.

### Workflow Definition metadata and governance

Required, architecture-level, for future maintainability — not
implemented yet, just designed for now, per explicit review feedback.
Every `WorkflowDefinition` row carries:

- **`version`** — the immutable integer discussed above.
- **`status`** — `DRAFT` / `ACTIVE` / `DEPRECATED`, a *definition*-level
  lifecycle, deliberately distinct from and never to be confused with
  the *instance*-level state machine in section 4 (an instance's
  `RUNNING`/`WAITING`/`COMPLETED` says "how is this one execution
  doing"; a definition's `status` says "is this version currently
  eligible to start new executions at all"):
  - `DRAFT` — being authored/tested. Never matches a trigger event,
    never starts an instance, freely editable in place (the only status
    where in-place editing is allowed at all).
  - `ACTIVE` — eligible to start new instances. **At most one version
    per `key` may be `ACTIVE` at a time** — the same "exactly one
    current row per group" discipline `OutreachDraft.is_current` already
    established in this codebase, applied here as a `status` value
    instead of a boolean for readability, since a definition also needs
    the `DRAFT`/`DEPRECATED` states a plain boolean can't express.
    Activating a new version is a single authoring action that
    atomically (a) sets the new version's `status = ACTIVE` and (b)
    demotes whichever version of that `key` was previously `ACTIVE` to
    `DEPRECATED` — this is definition-lifecycle bookkeeping done once,
    at publish time, by a human/operator action; it is categorically
    different from "migrating a running instance" (which never happens,
    per the invariant above) because it only changes which version
    *new* trigger events resolve to.
  - `DEPRECATED` — no longer eligible to start new instances, but never
    deleted and never made unreadable: every already-running instance
    pinned to a `DEPRECATED` version keeps executing against it,
    normally, to completion. A `key` is allowed to have **zero**
    `ACTIVE` versions at once (every version `DEPRECATED`, none
    promoted yet) — this is a valid, intentional way to pause a
    workflow from starting new instances without needing to invent a
    replacement version first.
- **`created_at`** / **`updated_at`** — standard bookkeeping timestamps
  (the same `TimestampMixin` convention already applied to every table
  in this project). `updated_at` matters less here than on most tables,
  precisely *because* `ACTIVE`/frozen versions are immutable — in
  practice it only ever moves when `status` itself transitions
  (`DRAFT → ACTIVE → DEPRECATED`), never when the step graph changes,
  since the step graph can't change once a version leaves `DRAFT`.

Further governance metadata (an author/owner field, a human-readable
changelog per version, approval sign-off tracking) is a natural,
additive extension of this same row shape — not designed or built now,
noted only so a future pass has an obvious place to attach it.

### Workflow Definition compatibility policy

The versioning invariants and `status` lifecycle above imply a set of
rules; this subsection states them directly, as the explicit governance
contract, so nothing about how a `WorkflowDefinition` may or may not
change is left to be inferred:

- **Once a version becomes `ACTIVE`, it is immutable.** Every field on
  that row — trigger clause, step graph, everything — is frozen from
  that moment on.
- **`ACTIVE` definitions cannot be edited.** Not by an admin tool, not by
  a migration, not by any engine process. There is no "hotfix an
  `ACTIVE` version in place" path, ever.
- **`DEPRECATED` definitions cannot be edited.** Retirement doesn't
  reopen editability — a `DEPRECATED` row is exactly as frozen as it was
  the moment before it stopped being `ACTIVE`, for exactly the same
  reason: instances still running against it are still depending on it
  being unchanged.
- **`DRAFT` definitions may be freely modified until published.** This is
  the *only* status where in-place editing is permitted — a `DRAFT` row
  isn't live, matches no trigger, and starts no instance, so changing it
  affects nothing yet running.
- **Publishing a change always creates a brand-new version.** There is
  no operation that "updates" an existing `(key, version)` row's
  behavior — publishing is `DRAFT → ACTIVE` for a *new* `version` number,
  never an edit to a prior one. This is the mechanism, restated from the
  Versioning subsection above: `version + 1`, not a patch.
- **Running `WorkflowInstance`s always remain pinned to the exact
  definition version they started with**, for their entire lifetime,
  with no exception.
- **There is no automatic or manual engine-driven migration of a running
  instance to a different definition version.** Not a background job,
  not an admin action, not a side effect of activating a new version.
  Activating v4 changes only what v-number a *future* trigger event
  resolves to (section 3's Metadata subsection) — it has zero effect on
  any instance already pinned to v1/v2/v3.

**The only supported way to change workflow behavior is to publish a new
version.** If a running instance needs to reflect that new behavior, the
only path is the operator-driven one already stated under Versioning:
cancel the old instance and let a fresh trigger event start a new one
against the new version. The engine itself has no concept of "upgrade
this instance in place" — that isn't a missing feature, it's a
deliberate absence, because an instance silently changing behavior
mid-execution is exactly the failure mode this whole policy exists to
rule out.

### Workflow Instances

One row per actual running (or completed) execution, created the moment
a trigger event matches. Carries: `workflow_definition_id` **and** the
exact `version` pinned at creation (an in-flight instance never changes
behavior because someone published a newer definition version — same
reasoning as `OutreachDraft` pinning its source `PersonalizationSnapshot`
version), `company_profile_id`, `subject_type`/`subject_id`, `status`
and `current_step_id` (section 4), a `context` JSONB blob (the
instance's own accumulated working data — the engine passes each
Action's output back into this blob as a pure pass-through; it never
reads or validates individual keys inside it, only Action handlers do),
and timestamps.

### Workflow execution

Step by step. Each step is exactly one Action invocation. The engine:
executes (or enqueues) the Action, receives a `SUCCESS`/`FAILURE`/
`RETRY`/`PENDING` outcome, evaluates that outcome against the step's
declared transition rules, and moves `current_step_id` forward — or into
`WAITING` if the step's own nature is "pause until an event/timer
arrives" (this is how "wait for human approval" or "wait for a reply" is
expressed generically, with zero domain knowledge — see section 6 for
how async/long-running domain work reuses this same mechanism).

### Workflow lifecycle

See the full state diagram in section 4. Summary: `PENDING → RUNNING ⇄
WAITING → COMPLETED / FAILED / CANCELLED`, plus an operator-only
`SUSPENDED` state distinct from the normal `WAITING` (e.g. "pause every
workflow for this business because their mailbox connection broke" is a
human intervention, not an expected part of any flow).

---

## 4. Workflow state machine

### Instance-level states

```
                    ┌─────────┐
     trigger event  │ PENDING │
     matched  ─────►│         │
                    └────┬────┘
                          │ dispatcher picks up
                          ▼
                    ┌─────────┐   step succeeds, more steps remain
              ┌────►│ RUNNING │────────────────┐
              │     └────┬────┘                │
              │          │                      │
   event/timer│          │ step declares         │
   arrives    │          │ "wait for X"          │
              │          ▼                      │
        ┌──────────┐                             │
        │ WAITING  │                             │
        └────┬─────┘                             │
              │ timeout fires,                    │
              │ no on_timeout rule                 │
              ▼                                    │
        ┌──────────┐   step fails, retries          │
        │  FAILED   │◄─exhausted, no on_failure ────┘
        └──────────┘   rule defined
              ▲
              │ operator action (not a normal transition)
        ┌──────────┐
        │SUSPENDED │◄──── operator pauses a RUNNING or WAITING instance
        └────┬─────┘
              │ operator resumes
              └──────────────► back to RUNNING or WAITING (whichever it was)

     RUNNING ──── all steps complete ────► COMPLETED
     RUNNING/WAITING/PENDING ── operator cancels ────► CANCELLED
```

### Step-level states (within one instance)

`PENDING → RUNNING → SUCCEEDED | FAILED | SKIPPED`, with `FAILED`
looping back to a fresh `RUNNING` attempt while `attempt_number <
max_attempts` (`RETRYING` is really `FAILED` immediately followed by a
new `PENDING`/`RUNNING` row for the next attempt — see
`workflow_step_invocations` in section 7, which records **every**
attempt as its own row, not an overwritten counter, for explainability).

### Branching and parallelism — explicitly scoped for v1

A step's transition rules already support **branching** (different next
step depending on outcome) at no extra cost. **Parallel fork/join
(multiple concurrent next-steps, waiting for all of them before
proceeding) is explicitly out of scope for v1** — the step-graph model
doesn't preclude adding it later (a step's "next" is already a *rule
set*, not a single hardcoded pointer, so extending one step to fan out
into several concurrent ones is additive, not a redesign), but nothing
in the current pipeline (Discovery → ... → Reply Intelligence) actually
needs parallel branches yet, and building it speculatively repeats
exactly the anticipatory-schema mistake this project has walked back
from before (see `future-milestones.md`'s own history on this).

---

## 5. Workflow worker architecture

### Two dedicated workers, not one — an explicit decision needing sign-off

Mirroring the exact reasoning M6.3 used to justify a dedicated Thread
Builder worker over folding it into Mailbox Sync (independent poll
cadence, independent failure isolation, one slow concern must never
block the other): I'm proposing **two** new worker processes rather than
one combined "workflow worker," because the Workflow Engine is expected
to become the busiest, most central process in the whole system once
more than one pipeline routes through it.

- **`workflow_event_dispatcher_worker`** — polls the `events` table,
  matches against trigger clauses and `WAITING` subscriptions, creates/
  resumes `WorkflowInstance` rows, writes `EventConsumption` rows. Does
  **not** execute Actions — pure state-transition work, deliberately
  kept cheap and fast so the event backlog never grows unbounded even if
  Actions are slow.
- **`workflow_step_runner_worker`** — polls `WorkflowInstance`s that are
  `RUNNING` with a claimable next step, invokes the registered Action
  handler, records the outcome as a `workflow_step_invocations` row,
  evaluates transition rules, advances (or pauses) the instance.

**Alternative considered:** one combined worker. Simpler to operate
initially (one fewer service in `docker-compose.yml`), and I'm
explicitly flagging it as the other option — same "which is it" question
M6.3 adjustment #1 posed, and I'd rather have that call made explicitly
than assume it. My recommendation is still two, for the reason above.

### Worker lifecycle

Identical entrypoint discipline to every existing worker in this
project: same image, `wait-for-db → alembic upgrade head → exec
<command>` entrypoint, `from app.db import base as _base` mapper
registration, single-instance sequential loop (see Concurrency below for
why this is disclosed as today's ceiling, not a permanent limit),
configurable poll interval, fresh DB session per unit of work, one bad
item logged and skipped rather than crashing the process — the same
four-times-proven pattern from Delivery/Mailbox Sync/Thread Builder/
Reply Intelligence, not reinvented.

### Polling vs. event processing

Plain polling at a short interval, matching every other worker in this
project — not Postgres `LISTEN`/`NOTIFY`. `LISTEN`/`NOTIFY` would reduce
latency, but adds a different failure mode (reconnect/missed-notification
handling) this project has no precedent for yet. Flagged as a possible
low-latency enhancement later, not required for v1.

### Transactions

Each step invocation's *engine-side* bookkeeping (claim → invoke Action
→ write `workflow_step_invocations` row → advance instance state)
happens as one committed unit, matching the "fresh session per item,
commit per item" discipline used everywhere else. The one thing the
engine's transaction boundary **cannot** cover is the Action's own
external side effect (e.g. an actual Gmail API call) — that already
happened, outside any database transaction, by the time the engine tries
to record the outcome. This is the same class of problem M6.3 already
solved once for outbound correlation: a `SAVEPOINT` + catch/log/never-
raise so a bookkeeping failure can never *undo* an already-successful
side effect. The identical pattern applies here — if writing the
step-outcome fails after the Action already ran, the fix is to retry the
*write*, using the idempotency key so a subsequent attempt can detect
"this side effect already happened" via the Action handler's own
idempotency check (section 2), not to blindly re-run the Action.

### Concurrency

Multiple *different* instances processing in parallel is fine — they're
independent. The *same* instance must never be claimed by two workers at
once (would corrupt `current_step_id`/`context`). Enforced via a
`claimed_by`/`claimed_at` pair with a stale-claim timeout — the same
transient-claim-state precedent `DeliveryQueueItem.SENDING` already
establishes in this codebase.

**Worth calling out explicitly:** declaring a claim column now is a
departure from this project's usual "don't add anticipatory schema"
discipline — but concurrency-safety columns are structural plumbing, not
speculative business logic; the moment a second worker replica is ever
added, this column is needed on day one, not as a follow-up migration.
That distinction is why it's proposed now rather than deferred.

### Locking

Row-level claim via `UPDATE ... WHERE status = 'RUNNING' AND
(claimed_by IS NULL OR claimed_at < stale_threshold) RETURNING id` —
not `SELECT ... FOR UPDATE SKIP LOCKED` for v1, consistent with every
other worker's disclosed single-replica simplification in this project.
`SKIP LOCKED`-based claiming is the natural, additive upgrade the moment
this worker is ever scaled beyond one replica (see section 11).

### Retry strategy

Per-step `max_attempts` + exponential backoff — same
`attempt_count`/backoff-reserved-for-later precedent already declared
(unused so far) on `MailboxSyncState`/`DeliveryQueueItem`. A step
exhausting its retries either follows an explicit `on_failure`
transition (routing to a dedicated failure-handling step, if the
definition author declared one) or, absent that, terminates the whole
instance as `FAILED`. `FAILED` is deliberately the *fallback*, not the
only outcome of a failed step — definitions are expected to often handle
failure explicitly.

---

## 6. Generic action system

An **Action** is the *only* way a workflow step does real work, and the
only place domain knowledge is allowed to live. Identified by a plain
string `action_key` (e.g. `"outreach.generate_draft"`,
`"delivery.enqueue_send"`) — same "adding one is a registry entry, never
a migration" convention as `provider_key`/`channel_key`. Registered in
an Action Registry that is **code, not a database table** (see the
rejected alternative in section 13) — an exact mirror of the
`PROVIDER_REGISTRY`/`CREDENTIAL_STORE_REGISTRY`/`REPLY_CLASSIFIER_
REGISTRY` pattern already used three times in this codebase.

**Fixed contract**, the entire surface the engine knows about:

```
execute(ActionInput) -> ActionOutput

ActionInput:
    workflow_instance_id, step_id, context (opaque JSONB), idempotency_key

ActionOutput:
    status: SUCCESS | FAILURE | RETRY | PENDING
    result: opaque JSONB, merged back into the instance's context
    error: optional, for FAILURE/RETRY
```

Each Action's *implementation* is a thin adapter living inside the
domain module that owns it (e.g. `app/outreach/workflow_actions.py`
would register `"outreach.generate_draft"` pointing at the *existing*
`app.outreach.pipeline` functions) — glue code, not a rewrite of
anything M1–M6 already built.

**Sync vs. long-running Actions — one unified mechanism, not two.** Some
Actions complete immediately (`SUCCESS`/`FAILURE`). Others kick off real
background work (an AI research call, a job that takes 30 seconds) — for
those, the Action returns `PENDING` immediately (its only real job was
"enqueue the underlying job and return"), and the instance stays
`RUNNING`/`WAITING` until the domain module later reports completion —
via an ordinary **Event** (e.g. `"research.job.completed"`) that the
Event Dispatcher picks up and uses to resume the instance. This is a
deliberate design choice: it means the engine needs no separate
"async-action callback" mechanism at all — long-running domain work is
just another instance of "a workflow waits for an event," identical in
kind to "wait for a human's approval" or "wait for a reply." One
mechanism, not two, is why this design is proposed.

---

## 7. Proposed database tables (concept only — no SQL, no migration)

- **`workflow_definitions`** — `key`, `version` (immutable, monotonic
  per `key`), `status` (`DRAFT`/`ACTIVE`/`DEPRECATED` — at most one
  `ACTIVE` row per `key`, see section 3's Metadata subsection for the
  full lifecycle), trigger `event_type`(s) + filter, step graph (JSONB),
  `company_profile_id` (nullable = platform-global), `created_at`,
  `updated_at`. (`is_active` from the original draft of this table is
  superseded by the richer `status` field above — a plain boolean can't
  express `DRAFT` vs `DEPRECATED`, both of which matter for governance.)
- **`workflow_instances`** — `workflow_definition_id` + pinned `version`
  (set once at creation from whichever row currently has `status =
  ACTIVE` for that `key`; never reassigned afterward, even after that
  version is later `DEPRECATED` — see section 3's versioning invariant),
  `company_profile_id`, `subject_type`/`subject_id`, `status`,
  `current_step_id`, `context` (JSONB), `claimed_by`/`claimed_at`,
  `started_at`/`completed_at`.
- **`workflow_step_invocations`** — one row per actual step *attempt*
  (append-only, never overwritten — the audit trail that makes the
  system explainable): `workflow_instance_id`, `step_id`, `action_key`,
  `attempt_number`, `status`, `input_snapshot` (JSONB), `output`
  (JSONB), `error`, `started_at`/`completed_at`.
- **`events`** — `event_id`, `event_type`, `occurred_at`, `sequence_no`,
  `company_profile_id`, `subject_type`/`subject_id`, `payload` (JSONB),
  `source`, `correlation_id`, `causation_id`, `schema_version`.
- **`event_consumptions`** — `event_id`, `workflow_instance_id`
  (nullable if this event *started* a new instance rather than resuming
  one), `consumed_at`, `outcome` (`started_new_instance` /
  `resumed_instance` / `no_match`) — unique on `(event_id,
  workflow_instance_id)`, the idempotency guarantee from section 2.
- **`workflow_timers`** — `workflow_instance_id`, `fires_at`, `status`
  (`pending`/`fired`/`cancelled`) — a small dedicated table so a timer
  sweep can cheaply find "what's due to wake up" without scanning every
  `WAITING` instance's JSONB for a deadline.

**Deliberately not a table:** Action registration (see section 6 and
the rejected alternative in section 13) — that stays code, matching
every existing registry in this project.

---

## 8. Integration with existing workers

Existing workers (Delivery, Mailbox Sync, Thread Builder, Reply
Intelligence) are **not** folded into the Workflow Engine and **not**
rewritten. Two small, additive integration points per module, both
optional and incremental (a module can be wired into the engine
gradually, one event/action at a time — not an all-or-nothing cutover):

1. **Event emission** — a `publish_event(db, ...)` call added at a
   module's own natural completion points, inside the *same* transaction
   as the domain write it's reporting (transactional outbox, section 2).
   E.g. `dispatch_service` gains a call after a successful send;
   `reply_intelligence_worker` gains one after writing
   `Conversation.reply_status`.
2. **Action registration** — where a workflow needs to *kick off* a
   module's existing work (e.g. "prospect qualified → generate a
   draft"), the registered Action does exactly what a human/API caller
   does today (calls the existing job-creation function) — not a
   reimplementation of Discovery/Research/Personalization/Outreach.

This keeps M7.1 what every milestone in this project has been so far:
additive glue around already-working modules, never a rewrite of any of
them.

---

## 9. Future AI agent integration

The Action contract (`ActionInput -> ActionOutput`, section 6) is
exactly what lets an AI-agent-backed Action slot in later with zero
engine changes: an Action whose implementation calls an LLM (with tool
access, planning, whatever) instead of/alongside deterministic domain
code satisfies the identical contract. The engine cannot tell, and does
not need to tell, whether a given `action_key` is backed by deterministic
code or an autonomous agent.

**Explicitly deferred, not built into v1:** AI-*authored* workflow
definitions (an AI system proposing or editing the step graph itself,
not just executing a step). `WorkflowDefinition`'s step graph is
versioned, JSONB-stored data, so this is technically reachable later
without a redesign — but v1 treats definitions as human/admin-authored
only, for predictability and safety. Flagged here as a real, deliberate
non-goal, not an oversight.

**Explainability is the connective tissue to AI-agent integration**: the
`workflow_step_invocations` audit trail plus the `correlation_id`/
`causation_id` event chain (section 2) is exactly the trace a human — or
a *supervising* AI agent — needs to answer "why did this happen," which
matters far more once an autonomous agent, not just deterministic code,
is making decisions inside a step.

---

## 10. Failure recovery

- **Step-level** — retry with backoff, then either an explicit
  `on_failure` transition or terminal instance `FAILED` (section 5).
- **Instance-level** — `FAILED` instances are never deleted; every
  `workflow_step_invocations` row remains inspectable to see exactly
  where and why. Manual retry/resume-from-failed-step is a real,
  useful future capability, explicitly not built in v1 (the schema
  doesn't preclude it — resuming just means creating a new attempt row
  and re-entering `RUNNING` at the failed step).
- **Worker-level** — identical "one item's failure must never poison the
  next" discipline already proven four times: fresh session per item,
  catch + log + continue, never crash the loop.
- **Event-processing-level** — if the dispatcher fails partway through
  matching one event against many instances, `EventConsumption`'s unique
  constraint means retrying that event is safe — already-matched
  instances are skipped, only the remainder is retried.
- **Stuck/stale claims** — `claimed_by`/`claimed_at` + a stale-claim
  timeout (section 5) makes a crashed worker's abandoned instance
  automatically reclaimable, mirroring `DeliveryQueueItem.SENDING`.
- **Poison pills** — after N consecutive failures, recommend a
  `DEAD_LETTER`-style terminal state rather than retrying forever, both
  for a single step and (as a circuit breaker) for a whole instance that
  somehow loops between two steps indefinitely (see Risks, section 14).

---

## 11. Performance and scalability

**v1, as designed:** single-instance, sequential-loop workers (two new
ones), matching every other worker's current ceiling in this project —
correctly sized for this product's actual current scale (a handful of
businesses), not a hypothetical one.

**Disclosed, additive scaling path, none of it built now:**
- `SELECT ... FOR UPDATE SKIP LOCKED` claiming, enabling multiple
  `workflow_step_runner_worker` replicas, the moment single-instance
  throughput is actually insufficient.
- Time- or `company_profile_id`-based partitioning of `events`/
  `workflow_step_invocations` if/when they grow very large — genuinely
  unbounded append-only tables, same disclosed concern as
  `DeliveryEvent`/`OutreachEdit` elsewhere, not solved here either.
- `LISTEN`/`NOTIFY` or an actual broker, only if/when real multi-region
  or extreme-throughput needs materialize — not needed today.

**Indexing (conceptual):** `events(company_profile_id, event_type,
occurred_at)` and `events(correlation_id)`; `workflow_instances(status,
company_profile_id)` for the runner's claim query;
`workflow_timers(fires_at)` partial index `WHERE status = 'pending'`.

**A real, unresolved risk worth naming here:** a single business running
a large number of concurrent instances could starve every other
business's processing in a naive global FIFO claim query. Mitigation
(round-robin or a per-company batch cap inside the claim query) is
proposed as a direction, not a solved design — see Risks.

---

## 12. Security and multi-business isolation

- Every `Event`/`WorkflowInstance`/(business-authored)
  `WorkflowDefinition` carries `company_profile_id` — the same
  tenant-scoping convention every table in this codebase has used since
  M1.
- **Shared-responsibility boundary, stated explicitly:** the engine
  guarantees an instance/event is correctly *scoped* and never
  cross-wired to the wrong company at the orchestration layer. It cannot
  and does not enforce domain-level row authorization itself, because it
  doesn't know what the domain data is — each Action implementation
  remains responsible for its own authorization checks, exactly as it is
  today, entirely outside the engine.
- Platform-global (`company_profile_id IS NULL`) definitions are
  author/edit-restricted to an admin/platform role; a business user
  (future multi-user) could only author/enable definitions scoped to
  their own `company_profile_id` — mirrors the existing `UserRole`
  `ADMIN`/`OPERATOR` precedent, not a new authorization concept.
- **Future multi-user:** v1 instances/definitions don't need a
  `user_id`-level owner (matching how most M1–M6 tables are
  company-scoped, not user-scoped) — but a future "which user approved
  this step" audit concept hooks in additively at the
  `workflow_step_invocations` row (an `actor_user_id` column when a
  human-approval Action is involved), not built now.
- **No new secrets/credentials concept.** Actions needing credentials
  (e.g. sending an email) keep using the existing `CredentialStore`/
  `ProviderConnection` machinery unchanged — the engine itself never
  touches a credential.

---

## 13. Alternatives considered

**A real message broker (Kafka/RabbitMQ/SQS) instead of a Postgres
`events` table.** Rejected for v1: every worker in this project already
runs single-instance, Postgres-only, with zero external broker
infrastructure — introducing one here would be the largest new
operational dependency in this project's history, for a scale it
doesn't operate at. Revisit only if real multi-region or extreme-
throughput needs actually materialize (section 11).

**Workflow logic as code (a hand-written `PipelineOrchestrator` class)
instead of declarative, JSONB-defined `WorkflowDefinition`s.** Rejected:
harder to make business-authorable or AI-editable later, harder to
version, far less explainable/inspectable than a stored step graph — and
directly contradicts the "modular"/"AI-first" design principles this
milestone was scoped against.

**Leave modules calling each other directly (today's reality) and add
observability on top, without a real orchestration primitive.**
Rejected: doesn't achieve explainability or future business-custom-
workflow goals, and direct cross-module calls are exactly the tight
coupling this milestone exists to eliminate.

**A database-backed Action Registry instead of code.** Rejected: every
existing registry in this codebase (`PROVIDER_REGISTRY`,
`CREDENTIAL_STORE_REGISTRY`, `REPLY_CLASSIFIER_REGISTRY`) is code, on
the explicit principle that adding a capability should be a deploy, not
a migration. No reason to break that precedent here.

**Mutable, in-place-edited `WorkflowDefinition`s (edit the step graph of
an already-`ACTIVE` version) instead of immutable versioned rows.**
Rejected, required by explicit review feedback: an in-flight
`WorkflowInstance` must never have its behavior change out from under it
mid-execution, which is only guaranteed if the version it's pinned to is
genuinely frozen the moment it goes live. Matches this codebase's
existing `OutreachDraft`/`PersonalizationSnapshot` precedent exactly.

**A plain `is_active` boolean instead of a `DRAFT`/`ACTIVE`/`DEPRECATED`
status field.** Rejected: a boolean can express "currently startable" or
not, but can't distinguish "still being authored, not ready to review"
from "was live, now retired" — both matter for governance, and
`workflow_step_invocations`/audit tooling benefits from being able to
tell the two apart when explaining why an old instance behaves the way
it does.

**One combined worker instead of two.** Not rejected — presented as a
genuinely open question in section 5, with a recommendation (two), not a
unilateral decision.

**Parallel fork/join workflows in v1.** Rejected for v1 as premature —
nothing in the current pipeline needs it yet, and the step-graph model
accommodates adding it later without a redesign.

---

## 14. Risks

1. **Premature abstraction.** The single biggest risk of this entire
   effort: building a fully generic engine before even one real
   workflow has run end-to-end against it. Mitigation: section 17's
   recommendation to implement against exactly one pilot workflow first.
2. **Multi-tenant fairness/starvation** (section 11) — a naive global
   FIFO claim query lets one large business's backlog starve every other
   business. Not solved in this document, flagged for the implementation
   phase.
3. **Dual-write/outbox discipline drift** — a future domain module
   simply forgetting to call `publish_event()` in the same transaction
   as its business write silently breaks orchestration for that event,
   with no error anywhere. Mitigation: a single shared helper + code
   review discipline for v1; a DB trigger-based alternative exists but
   is more "magic," harder to reason about, and only worth reconsidering
   if this failure mode actually recurs in practice.
4. **Unvalidated step graphs** — nothing today would catch a typo'd
   `action_key`, an unreachable step, or an accidental cycle in a
   `WorkflowDefinition` before its `status` is set to `ACTIVE`. Recommend
   a validation pass as a hard gate on the `DRAFT → ACTIVE` transition,
   required by the eventual implementation, not deferred indefinitely.
5. **Runaway instances** — a buggy definition looping between two steps
   forever. Recommend a built-in engine-level circuit breaker (hard
   max-step-count and/or max-duration per instance) rather than leaving
   this to individual definition authors to self-police.

---

## 15. Trade-offs, summarized

| Decision | Chosen | Cost |
|---|---|---|
| Postgres outbox vs. message broker | Postgres | Lower throughput ceiling; matches existing infra exactly |
| Declarative JSONB workflows vs. code | Declarative | No compile-time type safety on step graphs (mitigated by a validation pass) |
| Two workers vs. one | Two (recommended) | One more service to operate/monitor |
| Claim column now vs. deferred | Now | A small amount of schema that only matters once multi-replica exists |
| Sequential-only vs. parallel fork/join | Sequential + branching only | Some future workflows may need a follow-up design pass |
| Platform-authored only vs. business-authored in v1 | Platform-only (recommended) | Defers real "future multi-business" custom workflows |
| Single `ACTIVE` version per key vs. multiple simultaneously active (A/B testing) | Single `ACTIVE` (required, see section 3) | No native gradual-rollout/experimentation path yet — deferred, not precluded: `status` could grow a weighted-split concept later without changing the row shape |

---

## 16. Diagrams

### Sequence: one pilot workflow, end to end

```
Outreach          Workflow Engine                    Delivery         Reply Intelligence
   │                     │                                │                    │
   │ draft approved      │                                │                    │
   │  (event) ──────────►│                                │                    │
   │                     │ trigger matched, instance       │                    │
   │                     │ created, step 1 = "enqueue_send"│                    │
   │                     │ invoke Action ──────────────────►│                    │
   │                     │                                │ enqueue send        │
   │                     │◄────────────── SUCCESS ─────────┤                    │
   │                     │ step 2 = WAIT for "delivery.sent"│                    │
   │                     │ instance -> WAITING              │                    │
   │                     │                                │ ... time passes ... │
   │                     │◄──────── "delivery.sent" event ──┤                    │
   │                     │ instance -> RUNNING, resumes at  │                    │
   │                     │ step 3 = WAIT for "conversation. │                    │
   │                     │ reply.classified"                │                    │
   │                     │ instance -> WAITING               │                    │
   │                     │                                │                    │
   │                     │◄────────── reply classified event ─────────────────────┤
   │                     │ instance -> RUNNING, branches on  │                    │
   │                     │ reply_status (POSITIVE/NEGATIVE/  │                    │
   │                     │ NEUTRAL/OUT_OF_OFFICE)             │                    │
   │                     │ instance -> COMPLETED               │                    │
```

See sections 4 and 16's earlier diagrams for the module-boundary and
state-machine views.

---

## 17. Recommendations

1. **Do not implement the full generic engine against all six modules at
   once.** Scope the *first* real implementation to one pilot workflow —
   suggested: *"Draft approved → enqueue delivery → sent → wait for
   reply → reply classified → instance completes"* — since every module
   it touches already exists and already has natural completion points
   to hang an event on. Treat everything else in this document as the
   target shape, not the first PR.
2. **Decide the two open sign-off points explicitly**, same discipline
   as every prior milestone's approval round:
   - Two dedicated workers (recommended) vs. one combined worker
     (section 5).
   - Platform-authored-only definitions in v1 (recommended) vs. also
     shipping business-authored custom workflows now (section 3). I'd
     defer the latter — "future multi-user"/"AI-first" already signal
     it's coming, it doesn't have to be v1.
3. **Require the step-graph validation pass (Risk 4) and the runaway-
   instance circuit breaker (Risk 5) as non-negotiable parts of the
   first implementation**, not follow-ups — both are cheap to build now
   and expensive to retrofit once real `WorkflowDefinition`s exist in
   production.

**Architecture approved.** Next step is a separate implementation-
planning pass (pilot workflow scoping, concrete module/file layout,
migration sequencing) — not started yet, and still gated on its own
explicit go-ahead before any code or migration is written, per this
project's standing discipline.
