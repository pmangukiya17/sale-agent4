# M7.1 — Workflow Engine: Implementation Plan

**Status: plan only. Not authorized for implementation.** This document
describes *how* the already-approved architecture
(`m7-workflow-engine-plan.md`) will be built — no code, no migrations,
nothing here has been written. Every decision below is scoped to
preserve that architecture exactly: two dedicated workers, a Postgres
transactional outbox, `company_profile_id` as the only engine-level
tenant knowledge, opaque `subject_type`/`subject_id`, the unified
"waiting for events" mechanism, platform-authored definitions only,
immutable `DRAFT`/`ACTIVE`/`DEPRECATED` versioning, and — the constraint
repeated throughout this plan — exactly **one** pilot workflow, nothing
more.

---

## 1. Implementation Phases

Eleven phases, each small enough to review on its own, each depending
only on phases before it. Phases 0–6 build the generic engine and prove
it against synthetic, test-only definitions/actions — **zero real
domain module is touched until Phase 7.** This ordering is deliberate:
it lets the engine's own correctness be reviewed and verified completely
independently of whether the pilot's specific business logic is right,
mirroring how M6.3's threading algorithm was built and tested before
`dispatch_service.py` was touched.

### Phase 0 — Package scaffolding

- **Objective:** establish the engine's own package boundary before any
  table or logic exists, so the "zero import dependency from the engine
  into any domain package" rule (architecture section 1) is structural
  from day one, not something retrofitted later.
- **Files/modules:** `app/workflow_engine/__init__.py` (docstring only —
  same bootstrap-docstring precedent `app/reply_intelligence/__init__.py`
  set in M6.2's first phase, before any real code existed there).
- **Expected outcome:** an importable, empty package.
- **Dependencies:** none.
- **Verification:** `py_compile`. A grep-based structural check —
  `app/workflow_engine/` contains no `import app.discovery` / `app.
  research` / `app.personalization` / `app.outreach` / `app.delivery` /
  `app.reply_intelligence` anywhere — is introduced here and re-run as
  part of *every subsequent phase's* verification, not just this one.

### Phase 1 — Event infrastructure (schema + publish primitive)

- **Objective:** prove the transactional-outbox primitive works in
  complete isolation, before anything consumes it.
- **Files/modules:** `app/models/workflow_event.py` (the `Event` model),
  a new migration (`events` table only — see section 2), `app/
  workflow_engine/events.py` (`publish_event(db, ...)` — the only real
  logic in this phase).
- **Expected outcome:** a domain-agnostic table exists; a helper can
  insert a row into it from within an arbitrary caller's own open
  transaction.
- **Dependencies:** Phase 0.
- **Verification:** `tests/test_workflow_events.py` — a throwaway,
  test-only caller proves (a) a normal call commits a row with all
  fields correctly populated, (b) calling `publish_event()` and then
  rolling back the *outer* transaction correctly rolls back the event
  too (the concrete proof this is a real outbox, not a side-channel
  write on a separate connection). No real domain module calls this yet.

### Phase 2 — Workflow data model (schema only)

- **Objective:** land the full workflow model as pure, inert schema —
  no behavior anywhere in this phase.
- **Files/modules:** `app/models/workflow_definition.py`, `app/models/
  workflow_instance.py`, `app/models/workflow_step_invocation.py`,
  `app/models/workflow_timer.py`, `app/models/event_consumption.py`; new
  enums added to the existing `app/models/enums.py` (matching this
  project's single-enums-file convention, not a new file per model); a
  second migration (see section 2).
- **Expected outcome:** every table from the architecture doc's section
  7 exists; nothing reads or writes them yet outside tests.
- **Dependencies:** Phase 1 (the migration references `events`).
- **Verification:** `tests/test_workflow_models.py` — construct/persist/
  query round-trip for each new table (direct precedent:
  `test_conversation_models.py`'s own style from M6.1), plus a DB-level
  check that the partial-unique "at most one `ACTIVE` version per `key`"
  constraint (section 2) actually rejects a second `ACTIVE` row.

### Phase 3 — Action contract + registry

- **Objective:** define the one abstraction domain modules will
  eventually plug into, and prove the registry mechanics work, entirely
  in code — no DB, no real actions yet.
- **Files/modules:** `app/workflow_engine/actions/base.py`
  (`ActionInput`/`ActionOutput`/`Action` — the exact shape architecture
  section 6 specifies, itself a close mirror of `ReplyClassifier`'s own
  contract from M6.4), `app/workflow_engine/actions/registry.py` (code-
  based, mirroring `PROVIDER_REGISTRY`/`CREDENTIAL_STORE_REGISTRY`/
  `REPLY_CLASSIFIER_REGISTRY` exactly).
- **Expected outcome:** `register_action()`/`get_action()` work against
  a fake, test-only `Action` implementation.
- **Dependencies:** Phase 0 only (no DB needed).
- **Verification:** `tests/test_action_registry.py` — pure unit tests,
  no DB: register, resolve, unknown-key error behavior.

### Phase 4 — Workflow Definition governance logic

- **Objective:** implement the Compatibility Policy (architecture
  section 3) as enforced code, not just documented convention, and
  build the "resolve the `ACTIVE` version for this key" query the
  dispatcher will depend on in Phase 5.
- **Files/modules:** `app/workflow_engine/definitions.py` —
  `resolve_active_definition(db, key, company_profile_id)`,
  `validate_step_graph(step_graph, registered_action_keys)` (catches a
  typo'd `action_key`, an unreachable step, a cycle — architecture Risk
  4), `activate_definition(db, draft_definition)` (the atomic "set this
  version `ACTIVE`, demote the previous `ACTIVE` version of the same
  `key` to `DEPRECATED`" transition — the *only* place in the codebase
  permitted to perform this transition).
- **Expected outcome:** immutability is enforced at the service layer —
  every function here refuses to modify a non-`DRAFT` row; there is no
  other sanctioned code path to change a `WorkflowDefinition`.
- **Dependencies:** Phases 2, 3 (validation needs the registry).
- **Verification:** `tests/test_workflow_definitions.py` — DB-backed:
  activation correctly promotes/demotes in one transaction; attempting
  to "edit" an `ACTIVE` or `DEPRECATED` row through these functions is
  rejected; validation correctly rejects an unknown `action_key`, an
  unreachable step, and a cycle; a `key` with zero `ACTIVE` versions is
  a valid, queryable state.

### Phase 5 — Event Dispatcher worker

- **Objective:** the first of the two engine workers — matches events
  against definitions/waiting instances, creates/resumes instances.
  Invokes **no** Action.
- **Files/modules:** `app/workflow_engine/event_dispatcher_worker.py`
  (`run_one_tick()`/`run_forever()`, same shape as every existing worker
  in this codebase), config additions (poll interval), a new
  `workflow_event_dispatcher_worker` service in `docker-compose.yml`.
- **Expected outcome:** against a synthetic, test-only
  `WorkflowDefinition` (trigger on a fake `event_type`, one step), a
  published event correctly creates a new instance pinned to the right
  version, and a matching event correctly resumes a `WAITING` instance.
- **Dependencies:** Phases 1, 2, 4.
- **Verification:** `tests/test_event_dispatcher_worker.py` — DB-backed,
  same fixture discipline as `test_thread_builder.py`: new-instance
  creation, resume-from-waiting, `EventConsumption` idempotency (rerun
  is a true no-op), ignores `DRAFT`/`DEPRECATED` definitions, ignores
  wrong-tenant/wrong-filter events.

### Phase 6 — Step Runner worker

- **Objective:** the second engine worker — invokes Actions, records
  `workflow_step_invocations`, advances/pauses/completes/fails
  instances. **This is the last phase before any real domain code is
  touched** — everything through Phase 6 is proven against synthetic
  test doubles only.
- **Files/modules:** `app/workflow_engine/step_runner_worker.py`, claim/
  retry/backoff logic, config additions, a new
  `workflow_step_runner_worker` service in `docker-compose.yml`.
- **Expected outcome:** a `RUNNING` instance with a claimable step
  correctly invokes the registered Action, correctly transitions on
  `SUCCESS`/`FAILURE`/`RETRY`/`PENDING`, correctly retries with backoff
  up to `max_attempts`, correctly reaches `WAITING` when a step's action
  returns `PENDING` (proving the "async work reuses wait-for-event"
  unification from the architecture, against a fake long-running action).
- **Dependencies:** Phases 2, 3, 5.
- **Verification:** `tests/test_step_runner_worker.py` — DB-backed, a
  synthetic deterministic-outcome test `Action`: success path, retry-
  then-succeed, retry-exhaustion → `on_failure` transition vs. terminal
  `FAILED`, `PENDING` → `WAITING` → resumed-by-dispatcher round trip,
  claim/stale-claim reclaim (a concurrency test simulating two workers
  even though only one replica runs in production — see section 8).

**Checkpoint after Phase 6:** the generic engine is complete and fully
tested. Nothing beyond this line changes engine code — every remaining
phase is pilot-specific, additive glue.

### Phase 7 — Pilot Action: `delivery.enqueue_send`

- **Objective:** the pilot's one real Action.
- **Files/modules:** `app/delivery/workflow_actions.py` — a thin adapter
  registering `"delivery.enqueue_send"`, calling the *existing*
  enqueue/campaign-creation logic (no reimplementation), with its own
  idempotency check (section 7).
- **Expected outcome:** invoking this Action from a workflow step
  produces exactly the same `DeliveryQueueItem` a human/API call would
  produce today.
- **Dependencies:** Phase 3.
- **Verification:** `tests/test_delivery_workflow_action.py` — DB-backed:
  correct `DeliveryQueueItem` created on first call; idempotent rerun
  (same `idempotency_key`) does not create a duplicate.

### Phase 8 — Existing-worker event emission (the pilot's three touch points)

- **Objective:** wire the *only* three additive `publish_event()` calls
  this milestone makes into already-existing code — see section 4 for
  the full per-module breakdown and why only these three are touched.
- **Files/modules:** the existing OutreachDraft-approval code path
  (`"outreach.draft.approved"`), `app/delivery/dispatch_service.py`
  (`"delivery.sent"`, added at the exact spot M6.3 already added
  `_record_outbound_conversation()`), `app/reply_intelligence/
  reply_intelligence_worker.py` (`"conversation.reply.classified"`,
  added right after the existing `Conversation` field writes).
- **Expected outcome:** three events now get published, each inside the
  same transaction as the existing write it reports — and, critically,
  **nothing about existing behavior changes**, since no `ACTIVE`
  definition exists yet to react to them (see Rollout, section 10).
- **Dependencies:** Phase 1.
- **Verification:** for each of the three call sites, a test proving (a)
  the event is published with correct `event_type`/payload on the
  existing success path, and (b) forcing the existing transaction to
  roll back also rolls back the event (same proof as Phase 1, now
  against real call sites). Full existing M1–M6.4 regression suites
  re-run unchanged, confirming zero behavior drift outside the three
  additive lines.

### Phase 9 — Pilot Workflow Definition (data, not schema)

- **Objective:** author, validate, and — as a separate, deliberate final
  step — activate the one pilot `WorkflowDefinition`.
- **Files/modules:** a minimal CLI/one-off script (`app/workflow_engine/
  cli.py` or similar — not a migration, since a `WorkflowDefinition` row
  is data; not an admin UI, which is out of scope entirely for M7.1)
  that creates the pilot definition as `DRAFT`, runs Phase 4's
  validation, and — only on separate, explicit invocation — activates
  it.
- **Expected outcome:** exactly one `WorkflowDefinition` row exists for
  `key = "draft_approved_to_reply_classified"` (naming placeholder),
  `version = 1`, matching the step graph in section 5 below.
- **Dependencies:** Phases 4, 7, 8 (the trigger event and the one real
  action must both exist before this definition can validate).
- **Verification:** validation passes against the real registry
  (Phase 3) and the real trigger event type (Phase 8) — not synthetic
  test doubles this time. Activation is *not* performed as part of this
  phase's own verification — see Rollout, section 10, for why activation
  is deliberately its own, later step.

### Phase 10 — End-to-end verification

- **Objective:** the full-stack proof, mirroring every prior milestone's
  `verify_mN.sh` discipline.
- **Files/modules:** `verify_m7_1.sh` — full `docker compose up --build
  -d` including both new worker services, migration/schema checks,
  worker-log error-signature checks, the complete unit/integration/
  worker/failure-recovery test suites from every phase above, plus a
  scripted E2E scenario: activate the pilot definition, publish
  `"outreach.draft.approved"` for a real (or realistically fixtured)
  draft, confirm an instance is created and pinned to the correct
  version, confirm `delivery.enqueue_send` fires exactly once, confirm
  the instance reaches `WAITING`, publish the remaining two events in
  sequence, confirm the instance reaches `COMPLETED` with a correct,
  fully inspectable `workflow_step_invocations` audit trail. Closing
  disclosure section matching every prior verify script: a real send
  through a live provider is still outside what this script can prove,
  same disclosed boundary as M5/M6.
- **Dependencies:** every prior phase.
- **Verification:** itself — this phase *is* the verification gate for
  the whole milestone (see Completion Criteria, section 12).

---

## 2. Database Changes

Two migrations, in this order — split precisely at the point where the
first is fully independently useful without the second.

**Migration A — event infrastructure only.**
- New model: `Event` (`app/models/workflow_event.py`).
- New table: `events` — `event_id` (PK), `event_type`, `occurred_at`,
  `sequence_no` (identity/auto-increment — the true total-order tie-
  breaker, see architecture section 2), `company_profile_id` (FK to
  `company_profiles`), `subject_type`, `subject_id`, `payload` (JSONB),
  `source`, `correlation_id`, `causation_id`, `schema_version`.
- Indexes: `(company_profile_id, event_type, occurred_at)` — the
  dispatcher's own poll query; `(correlation_id)` — explainability
  lookups.
- Constraints: standard `NOT NULL` on `event_type`/`occurred_at`/
  `sequence_no`/`company_profile_id`. No uniqueness constraint on this
  table itself (idempotency is enforced downstream, on
  `event_consumptions`, not here).
- Depends on: nothing new — `company_profile_id` FKs to the existing
  `company_profiles` table only.

**Migration B — the workflow model.** One migration, not several,
because every table in it has a real dependency on another table also
introduced here (definitions → instances → step invocations/timers →
event consumptions), so splitting further would only produce
intermediate states with dangling FKs, not genuinely independent review
points.
- New models: `WorkflowDefinition`, `WorkflowInstance`,
  `WorkflowStepInvocation`, `WorkflowTimer`, `EventConsumption`.
- New enums (added to the existing `app/models/enums.py`, not new
  files): `WorkflowDefinitionStatus` (`DRAFT`/`ACTIVE`/`DEPRECATED`),
  `WorkflowInstanceStatus` (`PENDING`/`RUNNING`/`WAITING`/`SUSPENDED`/
  `COMPLETED`/`FAILED`/`CANCELLED`), `WorkflowStepInvocationStatus`
  (`PENDING`/`RUNNING`/`SUCCEEDED`/`FAILED`/`SKIPPED`),
  `EventConsumptionOutcome` (`STARTED_NEW_INSTANCE`/`RESUMED_INSTANCE`/
  `NO_MATCH`).
- New tables and their key constraints:
  - `workflow_definitions` — `key`, `version`, `status`, trigger
    `event_type` + filter, step graph (JSONB), `company_profile_id`
    (nullable = platform-global), `created_at`/`updated_at`. **Partial
    unique index on `(key)` WHERE `status = 'ACTIVE'`** — enforces "at
    most one `ACTIVE` version per key" at the database level, not only
    by service-layer discipline (Phase 4); direct precedent for this
    exact shape of constraint already exists in this codebase (the
    partial unique dedup index on `internet_message_id`, M6.1).
  - `workflow_instances` — `workflow_definition_id` (FK, `RESTRICT` —
    never allow a delete that would orphan instance history, same
    convention already used for `provider_connection_id` elsewhere) +
    pinned `version` (plain integer column, not a FK to a specific
    definition row — the pin is `(workflow_definition_id, version)`
    together), `company_profile_id`, `subject_type`/`subject_id`,
    `status`, `current_step_id`, `context` (JSONB), `claimed_by`/
    `claimed_at`, `started_at`/`completed_at`. Index on `(status,
    company_profile_id)` for the Step Runner's claim query.
  - `workflow_step_invocations` — `workflow_instance_id` (FK,
    `CASCADE` — pure child of an instance, same convention as
    `EmailMessage`/`ConversationParticipant` cascading from
    `Conversation`), `step_id`, `action_key`, `attempt_number`,
    `status`, `input_snapshot` (JSONB), `output` (JSONB), `error`,
    `started_at`/`completed_at`. Append-only — no update-in-place once
    a row is written, matching `DeliveryEvent`/`OutreachEdit`.
  - `workflow_timers` — `workflow_instance_id` (FK, `CASCADE`),
    `fires_at`, `status` (`pending`/`fired`/`cancelled`). Partial index
    on `(fires_at)` WHERE `status = 'pending'`.
  - `event_consumptions` — `event_id` (FK to `events`, `RESTRICT` —
    never delete a consumed event), `workflow_instance_id` (FK to
    `workflow_instances`, `CASCADE`, nullable — null only for the
    `NO_MATCH` outcome, where no instance is involved at all),
    `consumed_at`, `outcome`. **Unique constraint on `(event_id,
    workflow_instance_id)`** — the idempotency guarantee from
    architecture section 2, enforced at the database level.
- Depends on: Migration A (`events` must exist first for the
  `event_consumptions` FK).

No SQL, no actual migration file, is written as part of this plan — this
section describes shape and order only, per the explicit instruction.

---

## 3. Worker Changes

**Event Dispatcher worker** (`workflow_event_dispatcher_worker`).
Responsibility: read `events`, never write to any table this milestone's
pilot Action touches. For each unconsumed event (ordered by
`sequence_no`): resolve the `ACTIVE` `WorkflowDefinition` whose trigger
matches → create a `WorkflowInstance` pinned to that definition's exact
version, write `EventConsumption(outcome=STARTED_NEW_INSTANCE)`; find
every `WAITING` instance subscribed to this event → transition to
`RUNNING`, write `EventConsumption(outcome=RESUMED_INSTANCE)`; otherwise
write `EventConsumption(outcome=NO_MATCH)`. Never invokes an Action.

**Step Runner worker** (`workflow_step_runner_worker`).
Responsibility: read `workflow_instances` in `RUNNING` status with a
claimable next step, invoke the registered Action for `current_step_id`,
write a `workflow_step_invocations` row per attempt, evaluate the step's
transition rules, and advance/pause/complete/fail the instance
accordingly. Never reads `events` directly and never writes
`EventConsumption` — resuming a `WAITING` instance is exclusively the
Dispatcher's job.

**Interaction between them:** none direct — no call, no queue, no RPC.
They communicate purely through `WorkflowInstance.status` as shared
database state: the Dispatcher writes `RUNNING`, the Runner picks it up;
the Runner writes `WAITING`, the Dispatcher resumes it later on a
matching event. This is a direct restatement of the architecture's own
design — the implementation adds nothing here beyond what was already
approved.

**Failure handling, both workers:** identical, proven discipline —
fresh DB session per unit of work, one bad item logged and skipped, the
loop itself never crashes. A step's `on_failure` transition (if the
definition author declared one) is followed on retry exhaustion;
absent that, the instance terminates `FAILED`, never silently retried
forever.

**Retry behavior:** per-step `max_attempts` + exponential backoff, each
attempt recorded as its own `workflow_step_invocations` row (never
overwritten — the full retry history stays inspectable). The pilot's own
definition (section 5) sets concrete, conservative values for its one
real step, not left to a global default.

---

## 4. Existing Worker Integration

Only **three** additive `publish_event()` calls exist anywhere in this
milestone, at the pilot's exact touch points. Every other module listed
below is addressed for completeness (per the explicit ask to cover all
eight), but explicitly deferred — not wired in M7.1, because the pilot
does not need it and expanding further would violate the single-pilot
constraint (section 5).

| Module | This milestone | Hook point (if wired) / future hook point (if deferred) |
|---|---|---|
| Buyer Discovery (M1) | **Deferred** | Future: after a `DiscoveryJob` produces a qualified `Prospect`, e.g. `"prospect.qualified"`. |
| Research (M2) | **Deferred** | Future: after a `ResearchJob` completes, e.g. `"research.completed"`. |
| Personalization (M3) | **Deferred** | Future: after a `PersonalizationJob` completes, e.g. `"personalization.completed"`. |
| Outreach (M4) | **Wired — Phase 8** | The existing code path that transitions an `OutreachDraft` to `APPROVED` gains one additive `publish_event(db, event_type="outreach.draft.approved", ...)` call inside the same transaction as that status write. |
| Scheduling / Delivery (M5) | **Wired — Phase 8** | `dispatch_service.dispatch()`'s existing success path gains one additive `publish_event(db, event_type="delivery.sent", ...)` call, at the exact spot M6.3 already added `_record_outbound_conversation()`. |
| Mailbox Sync (M6.2) | **Deferred** | Not needed — the pilot's wait step is on Reply Intelligence's output, not raw sync. Future: after a sync tick, if ever useful, e.g. `"mailbox.synced"`. |
| Thread Builder (M6.3) | **Deferred** | Not needed — the pilot doesn't react to threading directly. Future: `"conversation.message.threaded"`. |
| Reply Intelligence (M6.4) | **Wired — Phase 8** | `reply_intelligence_worker.process_one_conversation()`'s existing success path gains one additive `publish_event(db, event_type="conversation.reply.classified", ...)` call, right after the existing `Conversation` field writes. |

**The general, minimal-change pattern**, restated once so it's obvious
how a future module gets wired in later: one `publish_event(db, ...)`
call, inside the existing transaction, at the module's own existing
completion point, using existing data to build the payload. No control
flow in the existing module changes; no existing function signature
changes; no existing caller of that module needs to know anything
happened.

---

## 5. Pilot Workflow

The one workflow this milestone builds — `key =
"draft_approved_to_reply_classified"` (naming placeholder, confirmable
at Phase 9), `version = 1`:

```
 trigger: "outreach.draft.approved"
      │
      ▼
 Step 1: action "delivery.enqueue_send"
      │  SUCCESS/PENDING → step 2
      │  FAILURE (retries exhausted) → instance FAILED
      ▼
 Step 2: wait for event "delivery.sent"
   (matched on subject_id = the same DeliveryQueueItem/draft)
      │
      ▼
 Step 3: wait for event "conversation.reply.classified"
   (matched on subject_id = the resulting Conversation)
      │
      ▼
 Step 4: complete
   (records reply_status into the instance's own context for
   visibility only — no branching business logic, no follow-up
   automation, no new email generation; instance → COMPLETED)
```

**Implementation detail, not a new architecture requirement:** Steps 2
and 3 invoke a small, engine-owned, reserved pseudo-action (something
like `"engine.wait_for_event"`) rather than having two different *kinds*
of steps in the Step Runner's execution model. This keeps "every step
invokes exactly one action" uniform — the pseudo-action always returns
`PENDING` with a subscription descriptor read from the step's own
config, which is exactly what the Dispatcher already needs to resume a
`WAITING` instance (section 3). This is purely an internal
simplification consistent with "waiting for events is the single
mechanism" from the approved architecture — it introduces no new
external behavior and no new domain knowledge.

**Explicitly not built in M7.1:** any second workflow, any branching on
`reply_status` into a new action, any follow-up-automation step, any
UI. All out of scope by the single-pilot constraint.

---

## 6. Transactions

- **Publishing** — inside the *same* transaction as the domain write it
  reports (Phase 1's proof, reused at all three Phase 8 call sites).
  Commit boundary is whatever the existing module's own commit already
  was; nothing changes here except one extra row going into that same
  commit.
- **Event Dispatcher, per unit of work** — one committed transaction per
  event: read → match → write instance/`EventConsumption` rows →
  commit. Fresh session per event, matching every existing worker.
- **Step Runner, per unit of work** — one committed transaction per step
  attempt: claim → invoke Action → write `workflow_step_invocations` row
  → advance/pause state → commit. **For this pilot specifically**, the
  one real Action (`delivery.enqueue_send`) is itself a plain database
  write (creating a `DeliveryQueueItem`), so its side effect genuinely
  can live inside the same transaction as the engine's own bookkeeping —
  there is no external API call in the pilot's critical path. The
  engine design still generically supports Actions with real external
  side effects (a future "send now" action would have one), via the
  same `SAVEPOINT` + catch/log/never-raise pattern M6.3 already
  established for outbound correlation: if the post-action bookkeeping
  write fails after a real external side effect already happened, retry
  the *write* (using the idempotency key to detect "already done"), never
  blindly re-run the *action*.
- **Rollback behavior** — any exception during either worker's unit of
  work rolls back that unit's transaction entirely; the item is left in
  its pre-attempt state, never partially written, and is picked up again
  on the next tick. Identical to every existing worker's own discipline.

---

## 7. Idempotency

- **Duplicate event prevention** — `event_consumptions`'s unique
  constraint on `(event_id, workflow_instance_id)` (Migration B). The
  Dispatcher's own processing of one event against one instance either
  succeeds once or, on a rerun, hits the constraint and is treated as
  "already done," not an error.
- **Replay behavior** — reprocessing an already-consumed event is a true
  no-op: the `EventConsumption` row already exists, so the dispatcher's
  write is skipped/caught rather than retried. This is what makes
  "rerun the dispatcher tick" always safe, including after a crash mid-
  tick.
- **Retry safety, the pilot's one real Action** — `ActionInput.
  idempotency_key` is derived as `f"{workflow_instance_id}:{step_id}"`,
  deliberately **attempt-independent** (every retry of the same step
  reuses the same key, per architecture section 2), so a retried
  invocation can recognize its own prior attempt. `delivery.enqueue_send`
  implements this by checking existing domain state before enqueueing —
  if a `DeliveryQueueItem` already exists for the underlying
  `OutreachDraft` (and isn't `CANCELLED`), the action returns `SUCCESS`
  immediately without creating a duplicate, rather than relying on any
  new engine-provided dedup mechanism. This is a concrete, minimal
  illustration of the architecture's stated division of responsibility:
  the engine guarantees a stable key, the Action owns what "already done"
  means for its own domain.

---

## 8. Concurrency

- **Locking** — row-level claim on `workflow_instances` via
  `claimed_by`/`claimed_at` + a stale-claim timeout, exactly as the
  architecture specifies (its own explicit exception to "don't add
  anticipatory schema," since a concurrency-safety column is structural
  plumbing needed from day one). Not `SELECT ... FOR UPDATE SKIP LOCKED`
  in this milestone — consistent with every existing worker's disclosed
  single-replica simplification.
- **Worker coordination** — none beyond the shared DB state described in
  section 3; the two worker *types* never coordinate directly, and
  within one worker type, only one process runs in v1.
- **Duplicate execution prevention** — the claim column prevents two
  workers from processing the *same* instance concurrently; `event_
  consumptions`'s unique constraint prevents the *same* event being
  applied to the *same* instance twice. Together these are the complete
  answer to "can this ever double-execute," and Phase 6 includes a
  concurrency test proving the claim mechanics work correctly even
  though only one replica runs in production today — worth testing now
  precisely because it's cheap to verify and expensive to discover
  broken later.
- **Scaling to multiple workers** — the natural, additive upgrade
  (disclosed, not built in M7.1): swap the claim `UPDATE` for `SELECT
  ... FOR UPDATE SKIP LOCKED`. No schema change required — `claimed_by`/
  `claimed_at` already exist for exactly this purpose.

---

## 9. Testing Strategy

- **Unit Tests** (no DB) — Action registry (Phase 3), step-graph
  validation (Phase 4), transition-rule evaluation, idempotency-key
  derivation. Fast, run anywhere.
- **Integration Tests** (DB-backed, no worker loop) — model round-trips
  (Phase 2), `publish_event()`'s transactional-outbox behavior including
  the rollback proof (Phases 1 and 8), definition activation/
  deprecation atomicity and the partial-unique-index constraint (Phase
  4), `EventConsumption` uniqueness (Phase 2/5).
- **Worker Tests** (DB-backed, `run_one_tick()` directly, no docker) —
  Dispatcher (Phase 5) and Step Runner (Phase 6) against synthetic test
  doubles, same fixture discipline as `test_thread_builder.py`/
  `test_reply_intelligence_worker.py`; the pilot Action (Phase 7)
  against real domain models.
- **Failure Recovery Tests** — retry-then-succeed and retry-exhaustion
  paths (Phase 6), stale-claim reclaim after a simulated crash (Phase
  6/8), a forced mid-tick exception followed by a rerun proving the
  system recovers to the correct state without duplication (Phases 5,
  6, 8).
- **End-to-End Tests** — `verify_m7_1.sh` (Phase 10): full docker stack,
  real pilot definition, a real event sequence from `"outreach.draft.
  approved"` through `COMPLETED`, asserting the full `workflow_step_
  invocations` audit trail.

**Verification milestone after every phase**, restated as a single
checklist: Phase 0 — package/import-boundary check. Phase 1 — outbox
round-trip + rollback proof. Phase 2 — model round-trips + constraint
check. Phase 3 — registry unit tests. Phase 4 — governance/validation
DB tests. Phase 5 — dispatcher worker tests. Phase 6 — step runner
worker tests + concurrency test. Phase 7 — pilot action tests +
idempotent-rerun proof. Phase 8 — three call-site tests + full existing
M1–M6.4 regression suite unchanged. Phase 9 — validation against the
real registry/event types. Phase 10 — `verify_m7_1.sh` green, full stop.

---

## 10. Rollout Strategy

Ordered specifically so the running system is **never** partially
broken at any point between phases:

1. **Phases 1–2 (schema)** — new tables only, nothing reads or writes
   them outside tests. Zero risk to the running system; completely
   inert.
2. **Phases 3–6 (engine core)** — the two new workers exist and poll,
   but find nothing to do (no real events flow into them yet). Zero
   behavior change to anything existing.
3. **Phases 7–8 (pilot action + event emission)** — three existing code
   paths gain one additive line each; events start getting recorded, but
   **no `ACTIVE` definition exists yet**, so the Dispatcher finds no
   trigger match for any of them — events are written and simply sit
   unconsumed. Still zero behavior change to any existing flow; the only
   new effect anywhere in the system is extra rows in an
   append-only table nothing else reads.
4. **Phase 9a — author + validate the pilot definition as `DRAFT`.**
   Fully reviewable, fully inert — a `DRAFT` row matches no trigger by
   definition.
5. **Phase 10 — run `verify_m7_1.sh` to full green** *before* the
   definition is ever activated. This script is the staging-equivalent
   gate this project doesn't otherwise have a separate environment for.
6. **Phase 9b — activate the pilot definition.** The **only** step in
   this entire rollout that turns on new, real behavior — a single,
   deliberate, explicit, and fully reversible action (immediately
   `DEPRECATED`-able again with zero data loss, per the Compatibility
   Policy) performed only after step 5 is green. Everything before this
   point could be deployed and left running indefinitely with no
   observable change to the product.

This ordering directly satisfies "never leave the system in a partially
broken state": every phase up to activation is purely additive and
inert by construction, not by care taken during rollout.

---

## 11. Risks

1. **A wired call site forgets the same-transaction discipline.**
   Mitigation: one shared `publish_event()` helper (never call the DB
   insert directly), a rollback-proof test at each of the three Phase 8
   sites specifically, code review.
2. **A broken pilot definition reaches `ACTIVE`.** Mitigation: Phase 4's
   validation pass is a hard gate on the `DRAFT → ACTIVE` transition,
   exercised against the real pilot definition in Phase 9 before
   activation, not just against synthetic test graphs.
3. **Claim/concurrency code is effectively unexercised in a single-
   replica deployment and silently wrong.** Mitigation: an explicit
   two-worker concurrency test in Phase 6 even though production runs
   one replica — cheap to write now, expensive to discover broken only
   after a future scale-out.
4. **Idempotency gaps in the one real pilot Action.** Mitigation: an
   explicit idempotent-rerun test for `delivery.enqueue_send`
   specifically (Phase 7), not just a generic engine-level idempotency
   test.
5. **Scope creep** — the temptation, mid-implementation, to wire in a
   second workflow or branch the pilot's final step into real business
   logic "while already in there." Mitigation: this plan enumerates the
   exact three touch points and the exact four-step graph; anything
   beyond that is out of scope for M7.1 by definition and belongs to a
   later, separately-approved milestone.
6. **Sandbox verification boundary** — same disclosed limitation as
   every prior milestone: no Docker/Postgres access in this environment,
   `py_compile` plus pure-logic unit tests are the ceiling here;
   `verify_m7_1.sh` and every DB-backed test in this plan needs to be
   run against the real stack and reported back, same established
   pattern as M6.2/M6.3/M6.4.

---

## 12. Completion Criteria

M7.1 is complete when all of the following are simultaneously true:

- All eleven phases (0–10) are implemented as described above.
- `verify_m7_1.sh` passes in full: schema/migration checks, both new
  worker services running with no error signature in their logs, and
  every unit/integration/worker/failure-recovery/end-to-end test green.
- Exactly one `WorkflowDefinition` exists (`draft_approved_to_reply_
  classified`, `version = 1`), has passed validation, and has been
  successfully activated.
- A real (or, given the disclosed sandbox boundary, a realistically
  fixtured) run reaches `COMPLETED`, with a `workflow_step_invocations`
  trail that correctly explains every transition it made.
- The three Phase 8 call sites are the **only** changes to any existing
  M1–M6.4 module, and the full existing regression suites for those
  milestones still pass unchanged.
- `app/workflow_engine/` has zero import dependency on any domain
  package, confirmed by the structural grep check introduced in Phase 0
  and re-run at every phase.
- No second workflow, no branching business logic, and no UI exist
  anywhere in the codebase as a result of this milestone.
- This document and `m7-workflow-engine-plan.md` both reflect the
  as-built reality, with any real deviation from this plan disclosed
  explicitly rather than silently — same discipline as every "as built"
  correction made to the M6 documents.

Waiting for approval before any phase begins.
