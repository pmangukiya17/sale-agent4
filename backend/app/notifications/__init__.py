"""
Notification Center - M8.5. A read-only CONSUMER of the platform Event
stream (app.models.workflow_event.Event / app.workflow_engine.events.
publish_event()), never a second source of truth and never a second
Event system - see the M8.5 architecture approval for why that decision
was non-negotiable.

Package boundary rules (mirroring app/workflow_engine/__init__.py's own
documented convention for what belongs in a top-level domain package
versus app/models//app/schemas//app/api/routes/):

  - This package NEVER writes to the `events` table. The only sanctioned
    writer of an Event is app.workflow_engine.events.publish_event(),
    called from inside whatever domain transaction produced it. This
    package only ever SELECTs from Event.

  - This package NEVER imports a concrete domain package (Discovery,
    Research, Personalization, Outreach, Delivery, Reply Intelligence,
    etc.). Symmetric to the Workflow Engine's own "domain modules import
    the engine, never the reverse" rule (see
    app/workflow_engine/actions/registry.py's own docstring) - a
    Notification rule is keyed by a plain `event_type` string (the same
    opaque, domain-owned vocabulary Event.event_type itself already
    uses), so a new domain module can start publishing events that this
    package reacts to WITHOUT this package ever importing that module by
    name. The import arrow always points from domain to notifications
    (a domain module could theoretically call
    app.notifications.rules.register_notification_rule() itself, though
    today every rule is registered as a built-in - see rules.py's own
    docstring), never the reverse.

  - This package owns exactly one new table pair:
      * Notification (app.models.notification.Notification) - the
        actual user-facing read/unread inbox row. Source of truth for
        "what should a human see", never for "what happened" (that's
        Event's job).
      * NotificationDispatch (app.models.notification.
        NotificationDispatch) - the idempotency/decision-tracking
        record of "has this Event already been considered for
        notification", directly mirroring EventConsumption's own
        precedent and reasoning (see that model's docstring) rather
        than inferring "not yet processed" from the mere absence of a
        Notification row, which would be ambiguous with "processed,
        decided not to notify".

  - rules.py: the extensible, code-based registry mapping `event_type`
    -> a notification content template. Adding a new notification is a
    code change here, never a migration - same "domain owns the string
    vocabulary" discipline as PROVIDER_REGISTRY/ACTION_REGISTRY/
    REPLY_CLASSIFIER_REGISTRY elsewhere in this codebase.

  - service.py: `create_notification_for_event()` - applies exactly one
    rule to exactly one Event and writes the resulting Notification +
    NotificationDispatch pair, transactionally, or writes only a
    "skipped" NotificationDispatch if no rule matches. Never invoked
    directly by a route; exclusively called from worker.py.

  - worker.py: the Notification Worker - a third standalone process,
    structurally identical to the Workflow Engine's own two workers (see
    event_dispatcher_worker.py's own docstring): polls Event ordered by
    `sequence_no` (the true total order), filtered to events with no
    NotificationDispatch row yet, fresh DB session per event, try/except/
    rollback/close per item so one bad event never poisons the loop.
    This is the ONLY code path anywhere that ever constructs a
    Notification row - the notifications API router
    (app/api/routes/notifications.py) is read/mark-read only, by design
    (see that router's own module comment).
"""
