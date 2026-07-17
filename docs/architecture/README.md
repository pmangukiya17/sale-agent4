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
