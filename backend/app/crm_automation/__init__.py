"""
CRM Automation - the deferred milestone from
docs/architecture/m6-reply-intelligence-plan.md section 5, approved and
scoped with adjustments (see that document's own M6.5 entry for the full
history of what changed and why).

Two modules, deliberately split by a hard rule: `state_machine.py` is
PURE - no database session, no imports of any model, every function a
plain value-in/value-out transformation, unit-testable with zero
fixtures. `service.py` is the only module in this package allowed to
touch a Session - it calls state_machine.py's functions, then performs
the actual writes (Prospect/ProspectContact columns,
ProspectTimelineEvent rows, Task rows) and publishes Events, inside
whatever transaction its caller already has open.

This package is deliberately NOT wired through the M7 Workflow Engine's
WorkflowDefinition/Action/Job model - relationship-stage transitions and
Task creation are instantaneous, deterministic bookkeeping reacting to
something that already happened (a send succeeded, a reply was
classified), not a multi-step AI execution with its own job/run history.
Forcing this through an async Action + Step Runner tick would add
latency for no reason and invent a fake "job" for something that isn't
one. Future-compatibility with Workflow Engine orchestration is
achieved differently: every transition/Task creation publishes a real
Event (app.workflow_engine.events.publish_event) onto the exact same
Event Backbone Notifications/Realtime/the Workflow Engine's own Event
Dispatcher already share. No BuiltinWorkflowDefinition subscribes to
these events today; a future milestone can register one against
RELATIONSHIP_STAGE_ADVANCED_EVENT_TYPE/TASK_CREATED_EVENT_TYPE with zero
change to this package.

service.py is called from exactly two existing, already-synchronous call
sites - never a new poller/worker:
    - app.delivery.dispatch_service.dispatch() - on a successful send
      (cold -> contacted, last_contacted_at).
    - app.reply_intelligence.reply_intelligence_worker.process_one_conversation()
      - right after Conversation.reply_status is written (contacted ->
        engaged -> qualified, last_replied_at, Task creation).

Explicitly out of scope for this milestone (per approval): reply_signal
scoring changes, any Discovery scoring engine change, time-based
follow-up generation, inactivity reminders, and any scheduled/cron-style
CRM automation. Nothing in this package runs on a timer.
"""
