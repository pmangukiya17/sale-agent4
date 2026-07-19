"""
Notification rule registry - the code-based mapping from an Event's
`event_type` to the Notification content that should be created for it.
Same plugin-registry discipline as REPLY_CLASSIFIER_REGISTRY/
PROVIDER_REGISTRY elsewhere in this codebase (see
app/reply_intelligence/classifiers/registry.py's own docstring): adding
a new notification is a code change here, never a migration, and never
a change to worker.py itself.

Deliberately the SIMPLE module-level self-registering dict pattern (a
plain module-level NOTIFICATION_RULES call to register_notification_rule()
below each rule function), not the ensure_builtin_actions_registered()
idempotent-guard pattern from app/workflow_engine/actions/registry.py.
That heavier pattern exists there to solve two problems neither of which
apply here: (1) a hard "the engine may never import a concrete domain
package" boundary, which forces the registration of the engine's own
built-in action to happen via a function-local import inside a guard
function rather than a plain module-level import; and (2) tests that
intentionally clear ACTION_REGISTRY for isolation, which would otherwise
wipe out that built-in. This module imports no domain package (a rule is
just a plain string key plus a static content template - see
NotificationRule below) and nothing in this codebase's test suite clears
NOTIFICATION_RULES, so the plain "self-register at import time" pattern
already used by REPLY_CLASSIFIER_REGISTRY is the right level of
machinery, not the Action Registry's heavier one.

A rule is intentionally NOT given the full Event to run arbitrary logic
over - just enough of it (payload, subject_type/subject_id) to compose
a title/message, keeping every rule a small, pure, deterministic
template function. This mirrors this project's "deterministic MVP, not
over-built" discipline elsewhere (e.g. event_dispatcher_worker.py's own
_matches_filter() docstring).
"""
from dataclasses import dataclass
from typing import Callable

from app.models.workflow_event import Event


@dataclass(frozen=True)
class NotificationContent:
    """The rendered result of applying one rule to one Event - exactly
    the fields Notification itself needs beyond what it already gets
    directly from the Event (company_profile_id, event_id)."""

    title: str
    message: str
    priority: str = "medium"


NotificationRule = Callable[[Event], "NotificationContent | None"]
# A rule may return None to mean "this event_type is registered but this
# specific event doesn't warrant a notification" - distinct from "no rule
# is registered for this event_type at all" (get_notification_rule()
# returning None). Both cases result in a "skipped" NotificationDispatch,
# never a Notification row - see service.py.

NOTIFICATION_RULES: dict[str, NotificationRule] = {}


def register_notification_rule(event_type: str, rule: NotificationRule) -> None:
    """Registers one rule under `event_type`. Re-registering an already-
    registered event_type raises - the same "no silent overwrite" guard
    as register_action()/PROVIDER_REGISTRY, for the same reason: two
    different call sites accidentally claiming the same event_type would
    otherwise fail silently, with the second registration just winning."""
    if event_type in NOTIFICATION_RULES:
        raise KeyError(f"Notification rule for event_type '{event_type}' is already registered")
    NOTIFICATION_RULES[event_type] = rule


def get_notification_rule(event_type: str) -> NotificationRule | None:
    """Existence + lookup in one call - used by service.py. Returns None
    (not a raise) for an unregistered event_type, since MOST event_types
    in this platform's stream are never expected to have a notification
    rule at all (that is the normal case, not an error) - only Events
    matching the growing built-in list below produce a Notification."""
    return NOTIFICATION_RULES.get(event_type)


# --- Built-in rules ---------------------------------------------------
# The M8.5 approved scope's own required "end-to-end proof using
# existing conversation.created events" - the one event_type this
# platform already publishes for real today (see
# app/reply_intelligence/thread_builder.py's own
# CONVERSATION_CREATED_EVENT_TYPE / _EVENT_SOURCE constants, reproduced
# here as a literal string rather than an import, since this package
# must never import a concrete domain package - see this package's own
# __init__.py docstring for why that boundary is symmetric with the
# Workflow Engine's "domain imports engine, never the reverse" rule).
CONVERSATION_CREATED_EVENT_TYPE = "conversation.created"


def _conversation_created_rule(event: Event) -> NotificationContent:
    """First real, working rule: every new conversation thread produces
    a medium-priority notification. Deliberately generic copy (no reach
    into the conversation's own subject/participants) since this rule
    has only the Event's own opaque payload to go on - a richer message
    (e.g. naming the contact) is a natural follow-up once Notification
    consumers want it, not a blocker for this milestone's end-to-end
    proof."""
    return NotificationContent(
        title="New conversation",
        message="A new conversation thread was created and is ready for review.",
        priority="medium",
    )


register_notification_rule(CONVERSATION_CREATED_EVENT_TYPE, _conversation_created_rule)
