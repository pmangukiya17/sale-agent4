"""
M7.1 Workflow Engine - a new, domain-agnostic orchestration layer that
sits above every existing domain module (Discovery, Research,
Personalization, Outreach, Delivery, Mailbox Sync, Thread Builder, Reply
Intelligence), coordinating cross-module handoffs through Events and
Workflows instead of direct code calls. See
docs/architecture/m7-workflow-engine-plan.md (the approved architecture)
and docs/architecture/m7-workflow-engine-implementation-plan.md (the
approved, phase-by-phase build plan this package is being built against)
for the full design. This is Phase 0 of that plan: package scaffolding
only - no models, no logic, no workers yet.

Structural boundary, enforced from this first phase onward, not
retrofitted later: this package (and every module added to it in later
phases) must have ZERO import dependency on any domain package -
`app.discovery`, `app.research`, `app.personalization`, `app.outreach`,
`app.delivery`, `app.reply_intelligence`. The engine's entire vocabulary
is Events (opaque `event_type` strings + opaque JSONB payload), Workflow
Definitions/Instances, Actions (opaque `action_key` strings + opaque
JSONB input/output), and state transitions - it must never know what an
email, a reply, a company, or a CRM is. Dependencies only ever point the
other way: a domain module will import this package's `publish_event()`/
`register_action()` helpers (added in later phases), never the reverse.

Models for this milestone's tables (Event, WorkflowDefinition,
WorkflowInstance, WorkflowStepInvocation, WorkflowTimer,
EventConsumption - Phases 1-2) will live in `app/models/`, not here -
matching this project's existing "models always live in app/models/,
only engine/service code gets its own per-milestone package" convention
(see e.g. app/reply_intelligence/__init__.py's own docstring, and
app/discovery/, app/research/, app/personalization/, app/outreach/,
app/delivery/ before it). Only orchestration logic (event publishing,
the two workers, the Action registry, workflow definition governance)
belongs in this package.

Part 1, Phase 5: the engine's one built-in action (the reserved
wait-for-event pseudo-action - see actions/wait_for_event.py) is
guaranteed to be registered by
app.workflow_engine.actions.registry.ensure_builtin_actions_registered(),
called internally from that same module's is_action_registered()/
get_action() - not by any import-order-dependent side effect of this
package's own __init__ (an earlier version of this file relied on
exactly that, and it silently broke the moment anything - e.g. a test's
own setUp() clearing ACTION_REGISTRY for isolation - ran after the
one-time self-registering import had already happened once per
process). See actions/registry.py's own docstring for the full
reasoning.
"""
