# Architecture documentation

This directory holds long-term architectural documentation for Sales Agent
— separate from the per-milestone implementation detail in the root
`README.md`, and meant to outlive any single chat session. If you are an
AI agent (or a person) picking up work on this repository without access
to prior conversation history, start here.

## Index

- [`future-milestones.md`](./future-milestones.md) — architectural
  guidance for M5 and beyond, written *before* those milestones were
  designed or approved. These are design constraints and intentions to
  build toward, not implementation tickets. Nothing in that document is
  authorized for implementation until it goes through the same
  proposal → refinement → explicit-approval process every milestone in
  this project has gone through (see the root `README.md` and git log
  for that history: `M0 Stable`, `M1.1 Complete`, `M1 Buyer Discovery
  Engine`, `M2 AI Research & Prospect Intelligence`, `M3 AI
  Personalization Engine`, `M4 AI Outreach Generation Engine`).
- [`m5-production-readiness.md`](./m5-production-readiness.md) — written
  at the close of M5 (Outreach Delivery Engine), after implementation.
  Unlike `future-milestones.md`, this documents decisions already made:
  the permanent (not sandbox-specific) boundary on what can be
  automatically tested without real provider credentials, the
  `CREDENTIAL_ENCRYPTION_KEY` rotation story, worker concurrency
  guarantees, and a re-confirmation that M5's actual code still matches
  the M6-readiness claims `future-milestones.md` note 9 made about it.
- [`m6-reply-intelligence-plan.md`](./m6-reply-intelligence-plan.md) —
  proposal for M6 (Reply Intelligence & Conversation Management),
  produced before implementation. Not authorized for implementation until
  explicitly approved — and it explicitly flags that its proposed design
  (persistent conversation storage) supersedes, rather than implements,
  `future-milestones.md` note 9's original ephemeral-only design. Read
  Decision Point 0 first. M6.1–M6.4 are implemented and verified; see
  that document's own phased-plan entries and "as built" sections for
  what actually shipped vs. the original draft.
- [`m7-workflow-engine-plan.md`](./m7-workflow-engine-plan.md) —
  architecture for M7.1 (Workflow Engine). **Design approved** (three
  review rounds: base architecture, then required additions for
  definition versioning/governance metadata, then a consolidated
  Workflow Definition Compatibility Policy subsection). Recommends
  implementing against one pilot workflow before wiring every module
  through the engine at once.
- [`m7-workflow-engine-implementation-plan.md`](./m7-workflow-engine-implementation-plan.md)
  — how M7.1 will be built: eleven small, independently-reviewable
  phases (engine core proven against synthetic test doubles in phases
  0–6, real domain wiring only from phase 7 onward), database/worker/
  transaction/idempotency/concurrency/testing/rollout detail, and exact
  completion criteria. Plan only — not authorized for implementation.
- [`m8-ui-ux-design-bible.md`](./m8-ui-ux-design-bible.md) — the
  frontend counterpart to the M0–M7 backend architecture: information
  architecture, navigation, design system (color/type/spacing/
  elevation/components), motion system, branding, responsive strategy,
  dashboard and page architecture, accessibility, and long-term
  scalability for the entire UI. Produced from nine dashboard concept
  images treated as one product, cross-referenced against the actual
  (at the time, unstyled, unbranded) `frontend/` codebase and the real
  backend data model built through M7.4. **Architecture approved (M8.7
  CEO review)**, with six amendments incorporated directly: a Design
  Debt Budget (Section 10.1), an explicit refactor-in-place migration
  method (Section 9.2), and confirmation that "UI must never invent
  state," the intentionally small token set, and the restrained,
  event-traceable motion system already satisfied the remaining review
  points as originally written. Its original real-time-push gap (Section
  13) is noted as superseded — M8.5/M8.6 have since shipped that
  infrastructure. Approval of this document is not, on its own,
  authorization to write React code — see the implementation plan below.
- [`m8-7-ui-ux-implementation-plan.md`](./m8-7-ui-ux-implementation-plan.md)
  — how the (approved) Design Bible will actually be built: six phases
  (A–F), weighted honestly against what M8.1–M8.4 already shipped rather
  than assuming a blank slate — Phases A–C are short confirmation/gap-
  closing passes over already-existing tokens/shell/dashboard code,
  Phase D fills the real remaining gaps in the component library
  (Select/Table/Modal/Toast/Tooltip), Phase E (the actual bulk of the
  work, split into CRM/AI-Workforce/Settings/Auth sub-phases) migrates
  the eighteen still-unstyled pages in place, and Phase F is a final
  motion/accessibility pass. Plan only — not authorized for
  implementation.
- [`deferred-items-and-design-boundaries.md`](./deferred-items-and-design-boundaries.md)
  — originally written at the close of M8.16 (World Map Geometry
  Verification) and M8.17 (Global Delete System); updated after the
  platform's first Comprehensive Verification pass (Track A) resolved two
  of the original items and added two more. Current contents: Discovery
  Search deletion (**resolved** — CASCADE-into-execution-history fixed to
  RESTRICT), ICP Criteria deletion (permanently excluded — contradicts
  the product's own "nothing is lost" versioning promise),
  Research/Personalization/Search Templates (no management UI exists yet
  to attach a delete button to), Company/Contact/ProspectContact
  lifecycle (ProspectContact **resolved** — real archive lifecycle plus
  the same CASCADE fix; Company/Contact superseded by their own
  retirement plan, see below), Workflow execution history (Job/Run/Event
  tables — a **permanent**, not deferred, immutability guarantee), a new
  **platform-wide lifecycle rule** generalizing archive-over-delete to
  any entity touching execution history, legacy Company/Contact model
  retirement (Phase 1 deprecation markers complete; Phase 2 removal is
  future work), and `POST /auth/register`'s interim admin gate pending M9
  Organization & AI Workforce Management. Read this before adding delete
  support anywhere in this codebase, adding a new execution-history table
  (the lifecycle rule applies automatically), or before assuming an
  entity's missing delete/archive action is an oversight.

## Conventions for documents in this directory

- Architectural intent, not implementation detail. Field lists, column
  types, and migration specifics belong in code and code comments, not
  here — those drift out of sync with prose the moment the schema
  changes. This directory should stay true by construction, not by
  discipline.
- Every design principle here should point at *why* the current,
  already-implemented architecture supports it, so a future reader can
  verify the claim against real code rather than take it on faith.
- Nothing here is a green light to build. Each item still needs its own
  explicit approval before implementation, exactly like every prior
  milestone in this project.
