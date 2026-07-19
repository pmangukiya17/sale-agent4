"""
create_notification_for_event() - applies the one registered rule (if
any - see rules.py) for a single Event to that Event, and writes the
resulting Notification plus its NotificationDispatch decision record.

Only ever called from worker.py, once per Event, inside that caller's
own fresh per-event session - never from a route (see
app/api/routes/notifications.py's own module comment: that router is
read/mark-read only).

Writes via add()+flush() only, never commit() - mirroring
app.workflow_engine.events.publish_event()'s own "the caller's
transaction commits atomically" discipline, so the Notification and its
NotificationDispatch decision record are always written together,
never one without the other.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationDispatch
from app.models.workflow_event import Event
from app.notifications.rules import get_notification_rule


def create_notification_for_event(db: Session, event: Event) -> Notification | None:
    """Returns the created Notification, or None if no rule is
    registered for event.event_type, or the matched rule itself
    declined (see NotificationRule's own docstring for that
    distinction). Either way, exactly one NotificationDispatch row is
    always written for this event_id - "decision already made,
    NotificationDispatch.notification_id is NULL" (decision="skipped")
    when no Notification was created, mirroring EventConsumption's own
    NO_MATCH precedent rather than leaving an ambiguous absence of any
    row - so this Event is never reconsidered by a later poll.
    """
    now = datetime.now(timezone.utc)
    rule = get_notification_rule(event.event_type)
    content = rule(event) if rule is not None else None

    if content is None:
        db.add(
            NotificationDispatch(
                event_id=event.id,
                notification_id=None,
                decision="skipped",
                dispatched_at=now,
            )
        )
        db.flush()
        return None

    notification = Notification(
        company_profile_id=event.company_profile_id,
        event_id=event.id,
        user_id=None,  # M8.5: no per-user targeting yet - see Notification's own docstring
        title=content.title,
        message=content.message,
        priority=content.priority,
        is_read=False,
        read_at=None,
    )
    db.add(notification)
    db.flush()  # assigns notification.id before it's referenced below

    db.add(
        NotificationDispatch(
            event_id=event.id,
            notification_id=notification.id,
            decision="notified",
            dispatched_at=now,
        )
    )
    db.flush()

    return notification
