from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.ai_gateway import ui_query
from app.ai_gateway.local_model_policy import delete_model_role, save_model_role
from app.ai_gateway.provider_config import save_provider_config
from app.ai_gateway.providers.registry import PROVIDER_CLIENT_REGISTRY
from app.api.deps import get_current_active_admin, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai_gateway import (
    ActivityLogEntryRead,
    AIProviderConfigAuditRead,
    ApprovalRequestRead,
    ConnectionTestResultRead,
    GatewayOverviewRead,
    GatewaySettingsRead,
    ModelRoleRead,
    ModelRoleWrite,
    ProviderConfigRead,
    ProviderConfigWrite,
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
# M8.2 was read-only end to end. M8.3 Step 2 (Provider Management) adds
# the first WRITE surface this router has ever had: PUT .../config (admin-
# gated, see get_current_active_admin) saves a DB-backed override via
# app.ai_gateway.provider_config.save_provider_config(); GET .../config and
# GET .../config/audit (both admin-gated) expose the override row and its
# lightweight change history; POST .../test-connection (any authenticated
# user, NOT admin-gated - it never mutates anything, it's a read-only
# connectivity probe) calls the real ProviderClient.test_connection().
#
# Still explicitly NOT implemented (see M8.2/M8.3 approved scope):
# settings persistence (GET /settings only - no PUT), approval ACTIONS (no
# POST to approve/reject - Approvals is read-only, see
# ApprovalRequestRead's own docstring for why there is nothing to action
# against), charts, live updates, polling, or WebSockets.


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


@router.get("/ai-gateway/providers/{provider_key}/config", response_model=ProviderConfigRead)
def get_provider_config(
    provider_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
) -> ProviderConfigRead:
    config = ui_query.get_provider_config(db, provider_key)
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown provider")
    return config


@router.put("/ai-gateway/providers/{provider_key}/config", response_model=ProviderConfigRead)
def put_provider_config(
    provider_key: str,
    body: ProviderConfigWrite,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
) -> ProviderConfigRead:
    """M8.3 Step 2 (Provider Management). Admin-gated (see
    get_current_active_admin - same precedent as POST /auth/register) -
    this is the first endpoint in this codebase that lets an operator
    change an AI provider's credentials/settings at runtime, without a
    backend restart (resolve_provider_config() takes no caching, so the
    very next AI Gateway call already sees this write - see that module's
    own docstring). Delegates entirely to
    app.ai_gateway.provider_config.save_provider_config() for the actual
    encrypt/merge/audit-row logic; this route's only job is translating
    the request body and committing the transaction."""
    if provider_key not in PROVIDER_CLIENT_REGISTRY:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown provider")

    try:
        save_provider_config(
            db,
            provider_key,
            changed_by_user_id=current_user.id,
            enabled=body.enabled,
            api_key=body.api_key,
            clear_api_key=body.clear_api_key,
            base_url=body.base_url,
            clear_base_url=body.clear_base_url,
            default_model=body.default_model,
            clear_default_model=body.clear_default_model,
            extra_settings=body.extra_settings,
        )
        db.commit()
    except ValueError as exc:
        # e.g. CREDENTIAL_ENCRYPTION_KEY unset - see
        # provider_config._encrypt_api_key()'s own docstring.
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ui_query.get_provider_config(db, provider_key)


@router.get("/ai-gateway/providers/{provider_key}/config/audit", response_model=list[AIProviderConfigAuditRead])
def list_provider_config_audit(
    provider_key: str,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
) -> list[AIProviderConfigAuditRead]:
    if provider_key not in PROVIDER_CLIENT_REGISTRY:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown provider")
    return ui_query.list_provider_config_audit(db, provider_key, limit=limit)


@router.get("/ai-gateway/model-roles", response_model=list[ModelRoleRead])
def list_model_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
) -> list[ModelRoleRead]:
    """M8.3 Step 3 (Model Role Management). Admin-gated, same precedent as
    Provider Management's config routes - a role -> model assignment is
    instance-wide infrastructure configuration, not a per-user preference.
    Returns only roles that actually have a saved DB row - see
    `ui_query.list_model_roles()`'s own docstring for why there's no
    fixed universe to synthesize placeholders for."""
    return ui_query.list_model_roles(db)


@router.put("/ai-gateway/model-roles/{role_name}", response_model=ModelRoleRead)
def put_model_role(
    role_name: str,
    body: ModelRoleWrite,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
) -> ModelRoleRead:
    """M8.3 Step 3. Creates a brand-new role (requires `body.model`) or
    updates an existing one. Per CEO decision #2, this ONLY ever affects
    `LocalOllamaProviderClient._resolve_model()` (via
    `app.ai_gateway.local_model_policy.resolve_local_model()`'s DB-lookup
    layer) - it can never change which PROVIDER a capability routes to,
    and it never touches any cloud ProviderClient. Delegates entirely to
    `local_model_policy.save_model_role()` for the actual create/update
    logic; this route's only job is translating the request body and
    committing the transaction."""
    try:
        save_model_role(
            db,
            role_name,
            model=body.model,
            enabled=body.enabled,
            changed_by_user_id=current_user.id,
        )
        db.commit()
    except ValueError as exc:
        # e.g. a brand-new role_name saved without a `model` value.
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ui_query.get_model_role(db, role_name)


@router.delete("/ai-gateway/model-roles/{role_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model_role_route(
    role_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
) -> None:
    """M8.3 Step 3. Deletes the DB override for `role_name`, if one
    exists - reversible-by-recreating, never a hard data-loss risk (see
    `AIModelRole`'s own docstring); the role simply resolves via the
    `LOCAL_MODEL_ROLES` settings fallback again, exactly as it did before
    any DB row for it ever existed. 404s if there was nothing to delete,
    same "delete of a nonexistent resource is an error, not a silent
    success" convention this codebase's other DELETE routes already use."""
    deleted = delete_model_role(db, role_name)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No saved model role with that name")
    db.commit()


@router.post("/ai-gateway/providers/{provider_key}/test-connection", response_model=ConnectionTestResultRead)
def test_provider_connection(
    provider_key: str,
    current_user: User = Depends(get_current_user),
) -> ConnectionTestResultRead:
    """M8.3 Step 2. Deliberately NOT admin-gated - unlike the config
    read/write routes above, this never mutates anything and never
    exposes a credential (ConnectionTestResultRead carries no api_key
    field at all) - any authenticated user can check whether a provider
    is currently reachable, same trust level as the existing read-only
    GET /ai-gateway/providers/{provider_key}. Constructs a fresh
    ProviderClient instance (PROVIDER_CLIENT_REGISTRY[provider_key]())
    and calls its real test_connection() - see
    app.ai_gateway.providers.base.ProviderClient's own docstring for the
    contract every client implements (a cheap models-list call, never a
    real completion)."""
    provider_cls = PROVIDER_CLIENT_REGISTRY.get(provider_key)
    if provider_cls is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown provider")

    result = provider_cls().test_connection()
    return ConnectionTestResultRead(
        provider_key=provider_key,
        success=result.success,
        message=result.message,
        latency_ms=result.latency_ms,
        available_models=result.available_models,
    )
