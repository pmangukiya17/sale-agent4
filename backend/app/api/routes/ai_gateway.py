from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.ai_gateway import ui_query
from app.ai_gateway.providers.registry import PROVIDER_CLIENT_REGISTRY
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai_gateway import (
    ActivityLogEntryRead,
    ApprovalRequestRead,
    GatewayOverviewRead,
    GatewaySettingsRead,
    ProviderSummaryRead,
    RoutingDecisionRead,
)

router = APIRouter()

# Read-only AI Gateway UI domain API (M8.2 - AI Gateway Backend
# Integration). Workspace-scoped (current_user only, no
# /company-profiles/{id}/... prefix) - matches AI Gateway's own IA
# decision (docs/architecture/ai-gateway-ux-architecture.md Section 1:
# workspace-scoped infrastructure, unlike company-scoped AI Workforce),
# and the same top-level-route precedent workspace_settings.py already
# establishes for a workspace-scoped resource.
#
# Explicitly NOT implemented in this milestone (see M8.2 approved scope):
# provider configuration (no POST/PUT to change a provider's credentials -
# those remain deployment-level app.core.config.settings env vars),
# settings persistence (GET /settings only - no PUT), approval ACTIONS (no
# POST to approve/reject - Approvals is read-only, see
# ApprovalRequestRead's own docstring for why there is nothing to action
# against), charts, live updates, polling, or WebSockets - every route
# below is a plain, synchronous GET computed fresh on each call.


@router.get("/ai-gateway/overview", response_model=GatewayOverviewRead)
def get_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GatewayOverviewRead:
    return ui_query.get_overview(db, current_user)


@router.get("/ai-gateway/providers", response_model=list[ProviderSummaryRead])
def list_providers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProviderSummaryRead]:
    return ui_query.list_providers(db)


@router.get("/ai-gateway/providers/{provider_key}", response_model=ProviderSummaryRead)
def get_provider(
    provider_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProviderSummaryRead:
    if provider_key not in PROVIDER_CLIENT_REGISTRY:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown provider")
    summary = ui_query.get_provider(db, provider_key)
    if summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown provider")
    return summary


@router.get("/ai-gateway/activity", response_model=list[ActivityLogEntryRead])
def list_activity(
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActivityLogEntryRead]:
    return ui_query.list_activity(db, current_user, limit=limit)


@router.get("/ai-gateway/approvals", response_model=list[ApprovalRequestRead])
def list_approvals(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ApprovalRequestRead]:
    return ui_query.list_approvals(db, current_user, limit=limit)


@router.get("/ai-gateway/routing", response_model=list[RoutingDecisionRead])
def list_routing_decisions(
    current_user: User = Depends(get_current_user),
) -> list[RoutingDecisionRead]:
    return ui_query.list_routing_decisions()


@router.get("/ai-gateway/settings", response_model=GatewaySettingsRead)
def get_settings(
    current_user: User = Depends(get_current_user),
) -> GatewaySettingsRead:
    return ui_query.get_settings()
