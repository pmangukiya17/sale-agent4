import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.prospect import Prospect
from app.models.prospect_timeline_event import ProspectTimelineEvent
from app.schemas.prospect_timeline import ProspectTimelineEventRead

router = APIRouter()

# Read-only from the API's point of view - events are appended internally
# (by the pipeline, by approve/reject/archive, by manual edits) via
# ProspectTimelineEvent directly, never through a public write endpoint.
# event_type is a free string by design so a future AI agent can append a
# kind of event that doesn't exist yet, without an API or schema change.


@router.get(
    "/company-profiles/{company_profile_id}/prospects/{prospect_id}/timeline",
    response_model=list[ProspectTimelineEventRead],
)
def list_prospect_timeline(
    prospect_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[ProspectTimelineEvent]:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None or prospect.company_profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    stmt = (
        select(ProspectTimelineEvent)
        .where(ProspectTimelineEvent.prospect_id == prospect.id)
        .order_by(ProspectTimelineEvent.created_at)
    )
    return list(db.scalars(stmt).all())
