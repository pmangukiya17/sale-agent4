import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.ai_workforce.mapper import get_agent_activity, list_agent_activities, list_activity_trace
from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.schemas.ai_workforce import AgentActivityRead, AgentActivityState, AgentActivityTraceEntryRead

router = APIRouter()

# Read-only AI Workforce domain API (M8.4 backend addition). This route
# never touches WorkflowInstance/WorkflowStepInvocation directly, and
# never imports app.workflow_engine or app.supervisor - see
# app/ai_workforce/__init__.py for the full boundary this package
# enforces. Same ownership-scoping dependency
# (get_owned_company_profile) every other /company-profiles/{id}/...
# route in this codebase already uses.


@router.get(
    "/company-profiles/{company_profile_id}/ai-workforce/activities",
    response_model=list[AgentActivityRead],
)
def list_activities(
    state: AgentActivityState | None = Query(None),
    limit: int = Query(50, le=200),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[AgentActivityRead]:
    return list_agent_activities(db, profile.id, state_filter=state, limit=limit)


@router.get(
    "/company-profiles/{company_profile_id}/ai-workforce/activities/{activity_id}",
    response_model=AgentActivityRead,
)
def get_activity(
    activity_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> AgentActivityRead:
    activity = get_agent_activity(db, profile.id, activity_id)
    if activity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent activity not found")
    return activity


@router.get(
    "/company-profiles/{company_profile_id}/ai-workforce/activities/{activity_id}/trace",
    response_model=list[AgentActivityTraceEntryRead],
)
def get_activity_trace(
    activity_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[AgentActivityTraceEntryRead]:
    trace = list_activity_trace(db, profile.id, activity_id)
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent activity not found")
    return trace
