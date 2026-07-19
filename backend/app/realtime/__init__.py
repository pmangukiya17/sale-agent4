"""
Real-Time Event Streaming - M8.6. A pure, in-process CONSUMER of the
platform Event stream (app.models.workflow_event.Event), the same single
append-only table app/notifications/ already reads (see that package's
own docstring for the precedent this mirrors). This package never writes
to `events` and never introduces a second one - Server-Sent Events are
just another read path over data that already exists, exactly as
approved.

Package boundary rules, extending the same discipline
app/notifications/__init__.py already documents:

  - This package NEVER writes to the `events` table, and never imports a
    concrete domain package. It only reads Event rows by `sequence_no`
    (the platform's own total-order primitive) and fans them out to
    whichever HTTP connections are currently open for the matching
    `company_profile_id`.

  - This package deliberately does NOT re-publish Notifications as
    Events. Per the explicit M8.6 architecture decision: a Notification
    is a presentation-layer concern, not a business fact, and the Event
    stream must only ever represent the latter. The frontend's
    Notification Center subscribes to BOTH this stream (as a low-latency
    "something happened, go check" nudge) AND the existing Notification
    REST API (app/api/routes/notifications.py, the actual, authoritative
    source of what to display) - never to a derived "notification.
    created" Event that doesn't exist.

  - This package owns NO new persistent table. The two things it holds
    are both deliberately transient/in-process:
      * broadcaster.py's subscriber registry (which HTTP connections are
        open right now, and for which company_profile_id) - meaningless
        to persist; it describes THIS process's current live
        connections, not platform state.
      * tickets.py's stream tickets - stateless, short-lived JWTs (see
        that module's own docstring), verified by decoding, never looked
        up in a table.

  - This package deliberately does NOT introduce Postgres LISTEN/NOTIFY.
    poller.py polls `events` on a short interval instead - an explicit,
    approved architectural choice to keep exactly one operational model
    (polling) across every background capability in this platform,
    rather than adding a second one to shave a second or two of latency.
    See poller.py's own docstring.

  - This package structurally CANNOT be a separate worker process/
    container, unlike every worker in app/notifications/ or
    app/workflow_engine/. Those workers produce derived DATABASE state
    (a Notification row, a WorkflowInstance transition) - a separate
    process is fine because the result is durable and any process can
    read it back. This package's whole job is holding open HTTP
    connections and pushing to THIS process's in-memory subscriber
    queues - a second process would have its own, disconnected set of
    connections and queues, so the poller must run inside the same
    FastAPI process that's serving the streaming responses (wired into
    app.main's own `lifespan`, started once at startup, cancelled at
    shutdown - see poller.py's `start()`/`stop()`).
"""
