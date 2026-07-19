import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EventRead(BaseModel):
    """Read-only projection of the platform Event stream
    (app.models.workflow_event.Event) - the same single table the
    Workflow Engine's own Event Dispatcher reads, exposed here as a
    reusable, read-only API for the frontend (Activity Timeline,
    Analytics, future AI Status) and for the Notification worker's own
    debugging/observability. No write endpoint exists or should exist -
    events are only ever created via
    app.workflow_engine.events.publish_event(), inside the transaction
    of whatever domain write they report."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence_no: int
    event_type: str
    occurred_at: datetime
    company_profile_id: uuid.UUID
    subject_type: str | None
    subject_id: uuid.UUID | None
    payload: dict[str, Any] | None
    source: str
    correlation_id: uuid.UUID | None
    causation_id: uuid.UUID | None
    actor_type: str | None
    actor_id: str | None
    severity: str | None
    category: str | None
    created_at: datetime
