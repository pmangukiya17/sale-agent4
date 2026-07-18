import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ProviderConnectionStatus


class ProviderConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    provider_key: str
    external_account_email: str | None
    # A JSONB list of raw OAuth scope strings, not a structured
    # capability list - see ProviderConnection's docstring. The frontend
    # (or a future M6 "does this connection support Mailbox Brief" check)
    # inspects this directly rather than the API pre-computing capability
    # flags that would need to be kept in sync with the provider's actual
    # scope strings.
    scopes_granted: list[str] | None
    status: ProviderConnectionStatus
    connected_at: datetime | None
    disconnected_at: datetime | None
    last_verification_at: datetime | None
    last_verified_at: datetime | None
    last_verification_detail: str | None
    created_at: datetime
    updated_at: datetime


class ProviderConnectionAuthorizeUrlRead(BaseModel):
    """Returned by both the Connect and Reconnect endpoints - the
    frontend redirects the browser to authorize_url; nothing else in this
    response is needed at that point since the connection row doesn't
    exist yet (Connect) or isn't updated yet (Reconnect) until the OAuth
    callback completes the round trip."""

    authorize_url: str


class ConnectableProviderRead(BaseModel):
    """One entry from PROVIDER_REGISTRY (app/delivery/providers/registry.py)
    - lets the frontend render a "Connect Gmail" / "Connect Outlook" list
    without hardcoding provider keys or scope strings. Adding a provider
    to the registry makes it appear here automatically; no schema change
    needed."""

    provider_key: str
    send_scopes: list[str]


class ProviderConnectionCallbackBody(BaseModel):
    """Added post-hoc during Layer 5, not part of the original Layer 4
    set - the OAuth callback's shape only became concrete once Layer 5's
    frontend-hosted-callback + signed-state design was settled (see
    connection_service.py's docstring). code/state are exactly what
    Google/Microsoft appended to the frontend's redirect_uri as query
    parameters; the frontend's callback page reads them off its own URL
    and re-POSTs them here as an authenticated call."""

    code: str
    state: str
