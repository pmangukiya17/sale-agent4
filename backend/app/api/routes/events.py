import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.workflow_event import Event
from app.schemas.event import EventRead

router = APIRouter()

# Read-only - Events are only ever created via
# app.workflow_engine.events.publish_event() (see that module's own
# docstring); no route here or anywhere else constructs one directly.
# This is the M8.5 Event Backbone's read surface: "Latest Events" /
# "Event History" from the approved API design, scoped per business the
# same way every other company-scoped route in this codebase is.


@router.get("/company-profiles/{company_profile_id}/events", response_model=list[EventRead])
def list_events(
    event_type: str | None = Query(None),
    category: str | None = Query(None),
    severity: str | None = Query(None),
    subject_type: str | None = Query(None),
    subject_id: uuid.UUID | None = Query(None),
    since: datetime | None = Query(None),
    limit: int = Query(50, le=200),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[Event]:
    stmt = select(Event).where(Event.company_profile_id == profile.id)
    if event_type is not None:
        stmt = stmt.where(Event.event_type == event_type)
    if category is not None:
        stmt = stmt.where(Event.category == category)
    if severity is not None:
        stmt = stmt.where(Event.severity == severity)
    if subject_type is not None:
        stmt = stmt.where(Event.subject_type == subject_type)
    if subject_id is not None:
        stmt = stmt.where(Event.subject_id == subject_id)
    if since is not None:
        stmt = stmt.where(Event.occurred_at >= since)
    stmt = stmt.order_by(Event.sequence_no.desc()).limit(limit)
    return list(db.scalars(stmt).all())


@router.get("/company-profiles/{company_profile_id}/events/{event_id}", response_model=EventRead)
def get_event(
    event_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Event:
    event = db.get(Event, event_id)
    if event is None or event.company_profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event
