"""
ProviderConnection OAuth lifecycle routes - Connect, Reconnect, the
callback that completes either, Disconnect, Verify. See
connection_service.py and app/delivery/oauth_state.py for the actual
logic and the full reasoning behind the frontend-hosted-callback +
signed-state design (a Layer 5 decision, not what Layer 3 originally
assumed).

/callback is the one route in this file that is NOT nested under a
"fetch-then-act" pattern the way every other route in this codebase is -
there is no ProviderConnection row to look up yet on a fresh Connect (the
whole point of the callback is to create it). It is still fully
authenticated (get_owned_company_profile) and still defense-in-depth
checked against the signed state's own company_profile_id - see
complete_delivery_connection below.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.delivery.connection_service import (
    ConnectionError_,
    build_authorize_url,
    build_reconnect_authorize_url,
    complete_connection,
    decode_oauth_state,
    disconnect,
    verify_connection,
)
from app.delivery.credentials.registry import get_credential_store
from app.delivery.providers.registry import PROVIDER_REGISTRY
from app.models.company_profile import CompanyProfile
from app.models.provider_connection import ProviderConnection
from app.models.user import User
from app.schemas.provider_connection import (
    ConnectableProviderRead,
    ProviderConnectionAuthorizeUrlRead,
    ProviderConnectionCallbackBody,
    ProviderConnectionRead,
)

router = APIRouter()


@router.get("/delivery/providers", response_model=list[ConnectableProviderRead])
def list_connectable_providers(current_user: User = Depends(get_current_user)) -> list[ConnectableProviderRead]:
    """Global, not company-scoped (same convention as reference_data.py's
    lookups) - which providers are connectable is a deployment-wide fact
    (are the OAuth client id/secret set at all), not a per-business one.
    Filters out a registered-but-unconfigured provider (see
    EmailConnectionProvider.is_configured) rather than offering a Connect
    button that would fail immediately on code exchange."""
    return [
        ConnectableProviderRead(provider_key=provider_cls.key, send_scopes=provider_cls.send_scopes)
        for provider_cls in PROVIDER_REGISTRY.values()
        if provider_cls().is_configured()
    ]


@router.get(
    "/company-profiles/{company_profile_id}/provider-connections",
    response_model=list[ProviderConnectionRead],
)
def list_provider_connections(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[ProviderConnection]:
    stmt = (
        select(ProviderConnection)
        .where(ProviderConnection.company_profile_id == profile.id)
        .order_by(ProviderConnection.created_at.desc())
    )
    return list(db.scalars(stmt).all())


def _get_connection_or_404(db: Session, profile_id: uuid.UUID, connection_id: uuid.UUID) -> ProviderConnection:
    connection = db.get(ProviderConnection, connection_id)
    if connection is None or connection.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider connection not found")
    return connection


# --- literal-path routes below, deliberately registered BEFORE the
# {connection_id} routes further down: FastAPI/Starlette matches routes in
# registration order, and "connect"/"callback" would otherwise be
# swallowed by {connection_id} (Starlette matches the path shape first,
# then FastAPI tries - and fails - to parse "connect" as a UUID), the
# exact same ordering rule outreach_drafts.py already follows for its
# literal "current" path segment. ---------------------------------------


@router.get(
    "/company-profiles/{company_profile_id}/provider-connections/connect",
    response_model=ProviderConnectionAuthorizeUrlRead,
)
def start_provider_connect(
    provider_key: str,
    profile: CompanyProfile = Depends(get_owned_company_profile),
) -> ProviderConnectionAuthorizeUrlRead:
    """No side effects (state is a self-contained signed token, nothing
    is written to the database here) - GET is appropriate. The frontend
    redirects the browser to the returned authorize_url."""
    if provider_key not in PROVIDER_REGISTRY:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown provider_key '{provider_key}'")
    if not PROVIDER_REGISTRY[provider_key]().is_configured():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Provider '{provider_key}' is not configured on this server")
    url = build_authorize_url(company_profile_id=profile.id, provider_key=provider_key)
    return ProviderConnectionAuthorizeUrlRead(authorize_url=url)


@router.post(
    "/company-profiles/{company_profile_id}/provider-connections/callback",
    response_model=ProviderConnectionRead,
)
def complete_delivery_connection(
    body: ProviderConnectionCallbackBody,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProviderConnection:
    """Completes both Connect and Reconnect (see complete_connection's
    docstring). This is the one place the frontend's OAuth-callback page
    calls after Google/Microsoft redirects back to it - see this
    module's docstring and GMAIL_OAUTH_REDIRECT_URI/
    MICROSOFT_OAUTH_REDIRECT_URI in core/config.py for why that redirect
    now lands on the frontend rather than here directly.

    get_owned_company_profile already proves current_user owns
    {company_profile_id} in the URL. The explicit re-check below - that
    the signed state's OWN company_profile_id matches that same path
    value - is what actually closes the cross-tenant CSRF gap: state can
    only ever have been signed by build_authorize_url for a profile the
    ORIGINAL caller owned at connect-time (see oauth_state.py's
    docstring), so this mismatch can only fire if someone completes a
    connect/reconnect they didn't start themselves - exactly the case to
    reject.
    """
    try:
        decoded = decode_oauth_state(body.state)
    except ConnectionError_ as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if decoded.get("company_profile_id") != str(profile.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This connect/reconnect flow was not started for this business.",
        )

    credential_store = get_credential_store()
    try:
        return complete_connection(db, credential_store, code=body.code, state=body.state)
    except ConnectionError_ as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/company-profiles/{company_profile_id}/provider-connections/{connection_id}",
    response_model=ProviderConnectionRead,
)
def get_provider_connection(
    connection_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ProviderConnection:
    return _get_connection_or_404(db, profile.id, connection_id)


@router.get(
    "/company-profiles/{company_profile_id}/provider-connections/{connection_id}/reconnect",
    response_model=ProviderConnectionAuthorizeUrlRead,
)
def start_provider_reconnect(
    connection_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ProviderConnectionAuthorizeUrlRead:
    _get_connection_or_404(db, profile.id, connection_id)
    try:
        url = build_reconnect_authorize_url(db, connection_id)
    except ConnectionError_ as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ProviderConnectionAuthorizeUrlRead(authorize_url=url)


@router.post(
    "/company-profiles/{company_profile_id}/provider-connections/{connection_id}/disconnect",
    response_model=ProviderConnectionRead,
)
def disconnect_provider_connection(
    connection_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ProviderConnection:
    _get_connection_or_404(db, profile.id, connection_id)
    credential_store = get_credential_store()
    try:
        return disconnect(db, credential_store, connection_id)
    except ConnectionError_ as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/company-profiles/{company_profile_id}/provider-connections/{connection_id}/verify",
    response_model=ProviderConnectionRead,
)
def verify_provider_connection(
    connection_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> ProviderConnection:
    """Never raises for an expired/invalid credential - see
    EmailConnectionProvider.verify's docstring - so a 200 response with
    status=ERROR and last_verification_detail populated is the normal,
    expected outcome for a broken connection, not an exception. Only
    genuinely unexpected failures (connection not found, no credential
    store configured) become an HTTP error here."""
    _get_connection_or_404(db, profile.id, connection_id)
    credential_store = get_credential_store()
    try:
        return verify_connection(db, credential_store, connection_id)
    except ConnectionError_ as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
