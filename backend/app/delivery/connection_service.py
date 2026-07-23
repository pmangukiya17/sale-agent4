"""
ProviderConnection lifecycle: Connect, Reconnect, Disconnect, Verify -
first-class operations per the explicit M5 refinement, not just an
initial OAuth callback handler. Each is its own function, separate from
campaign_service/queue_service, because this is genuinely its own
responsibility (orchestrating provider OAuth calls + the credential
store), not a delivery-campaign concern.

`state` passed through the OAuth roundtrip is HMAC-signed (with
settings.SECRET_KEY) and time-bounded by app.delivery.oauth_state - see
that module's docstring for why signing is required (Layer 5 correction:
an authenticated completion endpoint alone is NOT sufficient without
tamper-proof state; the two together are what closes the cross-tenant
mailbox-swap CSRF gap). This module owns the secret; the route layer
(Layer 5) only ever calls the wrapper functions below and never sees
SECRET_KEY or the signing details directly.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.delivery.credentials.base import CredentialStore, CredentialStoreError
from app.delivery.oauth_state import OAuthStateError
from app.delivery.oauth_state import decode_oauth_state as _decode_oauth_state
from app.delivery.oauth_state import encode_oauth_state as _encode_oauth_state
from app.delivery.providers.base import (
    EmailConnectionProvider,
    IncrementalSyncCapable,
    ProviderAuthError,
    provider_supports_capability,
)
from app.delivery.scope_utils import top_up_scopes
from app.delivery.providers.registry import get_provider
from app.models.enums import ProviderConnectionStatus
from app.models.provider_connection import ProviderConnection

__all__ = [
    "ConnectionError_",
    "encode_oauth_state",
    "decode_oauth_state",
    "build_authorize_url",
    "build_reconnect_authorize_url",
    "complete_connection",
    "disconnect",
    "verify_connection",
    "refresh_credential_if_needed",
]


class ConnectionError_(Exception):
    """Raised for connection-lifecycle failures the API layer should
    surface as 400s (unknown provider, connection not found, no
    credential to verify) - distinct from ProviderAuthError/
    ProviderSendError, which are about live calls to the provider, not
    about the connection record itself. Named with a trailing underscore
    to avoid shadowing the builtin ConnectionError."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def encode_oauth_state(
    *, company_profile_id: uuid.UUID, provider_key: str, reconnect_connection_id: uuid.UUID | None = None
) -> str:
    """Thin wrapper over app.delivery.oauth_state.encode_oauth_state that
    injects settings.SECRET_KEY - callers (build_authorize_url /
    build_reconnect_authorize_url below, and the route layer) never
    handle the secret directly."""
    return _encode_oauth_state(
        company_profile_id=company_profile_id,
        provider_key=provider_key,
        reconnect_connection_id=reconnect_connection_id,
        secret=settings.SECRET_KEY,
    )


def decode_oauth_state(state: str) -> dict:
    """Thin wrapper over app.delivery.oauth_state.decode_oauth_state that
    injects settings.SECRET_KEY and re-raises as ConnectionError_ - the
    API layer only needs to handle one exception type from this module
    and never sees signing details."""
    try:
        return _decode_oauth_state(state, secret=settings.SECRET_KEY)
    except OAuthStateError as exc:
        raise ConnectionError_(str(exc)) from exc


def build_authorize_url(*, company_profile_id: uuid.UUID, provider_key: str) -> str:
    """Connect: a fresh connection, send-only scopes. Reconnect uses
    build_reconnect_authorize_url instead - kept as a separate function
    rather than an optional parameter here so the two call sites in the
    API layer stay unambiguous about which flow they're starting."""
    provider = get_provider(provider_key)
    state = encode_oauth_state(company_profile_id=company_profile_id, provider_key=provider_key)
    return provider.get_authorize_url(state, provider.send_scopes)


def build_reconnect_authorize_url(
    db: Session, connection_id: uuid.UUID, *, include_read_scopes: bool = False
) -> str:
    """Outlook Integration milestone (found during CEO-reported live
    testing, alongside the Mail.ReadWrite send fix - see
    outlook_provider.py's own docstring for the paired root cause).

    Previously this function re-requested EXACTLY the scopes already on
    `connection.scopes_granted` (falling back to `provider.send_scopes`
    only for a connection with none recorded yet) - a literal replay of
    history. That meant a product-side change to what a provider's
    send_scopes list requires (e.g. adding Mail.ReadWrite once M6.3's
    create-draft-then-send pattern needed it) would NEVER reach an
    already-connected business, no matter how many times they clicked
    Reconnect - the old code would just re-request the same, now-stale,
    too-narrow scope list forever.

    Fixed by always UNIONING `provider.send_scopes` (the provider class's
    CURRENT baseline requirement, read fresh every call) with whatever is
    already on the connection, deduplicated, order-preserving - so any
    plain Reconnect now "tops up" a connection to at least today's
    baseline automatically, without the caller needing to know that a
    scope requirement changed. This is what actually lets an existing,
    send-broken Outlook connection self-heal via the SAME Reconnect
    button that already existed - no new route, no new UI action, for
    this part.

    `include_read_scopes` (new, optional, default False - preserves the
    exact prior behavior for any caller that doesn't pass it) additionally
    unions in `provider.read_scopes` - the Mail.Read-class scopes
    IncrementalSyncCapable needs for mailbox sync. Deliberately a SEPARATE
    opt-in flag, not folded into the baseline top-up above: mailbox
    reading is a materially more sensitive grant than "can send/draft
    mail on your behalf," and this project's own M6.2 design already
    treats it as a real, explicit, user-driven decision (see
    sync_worker.py's has_read_scope docstring) - baseline send-scope
    repair must never silently smuggle in mailbox-read access as a side
    effect. Raises ConnectionError_ if the caller asks for read scopes on
    a provider that doesn't implement IncrementalSyncCapable at all
    (Gmail, today) rather than silently ignoring the flag - the same
    "fail loud on a caller error, not a provider limitation" discipline
    build_authorize_url's own callers already rely on.
    """
    connection = _get_connection_or_raise(db, connection_id)
    provider = get_provider(connection.provider_key)

    if include_read_scopes and not provider_supports_capability(provider, IncrementalSyncCapable):
        raise ConnectionError_(f"Provider '{connection.provider_key}' does not support mailbox reading yet.")

    state = encode_oauth_state(
        company_profile_id=connection.company_profile_id,
        provider_key=connection.provider_key,
        reconnect_connection_id=connection.id,
    )
    scopes = top_up_scopes(
        connection.scopes_granted,
        provider.send_scopes,
        additional=provider.read_scopes if include_read_scopes else None,
    )
    return provider.get_authorize_url(state, scopes)


def complete_connection(db: Session, credential_store: CredentialStore, *, code: str, state: str) -> ProviderConnection:
    """Handles both Connect and Reconnect - the OAuth code-exchange step
    is identical; only whether an existing row is updated vs a new one
    created differs, decided by whether `state` carries a
    reconnect_connection_id.

    ProviderAuthError (a failed code exchange - e.g. Microsoft's
    AADSTS50194 tenant mismatch) and CredentialStoreError (e.g.
    CREDENTIAL_ENCRYPTION_KEY unset) are both translated into
    ConnectionError_ here, at the one place both can occur during this
    flow - found during M5 Layer 7 verification to be missing entirely,
    which meant either failure reached the API layer as an uncaught
    exception (a raw 500 with no usable message) instead of the clean 400
    the route's `except ConnectionError_` handler already exists to
    produce. The route layer needs no change: it only ever has to know
    about ConnectionError_, exactly as before."""
    decoded = decode_oauth_state(state)
    provider_key = decoded["provider_key"]
    provider = get_provider(provider_key)
    try:
        token_payload = provider.exchange_code(code)
    except ProviderAuthError as exc:
        raise ConnectionError_(str(exc)) from exc

    reconnect_id = decoded.get("reconnect_connection_id")
    if reconnect_id:
        connection = _get_connection_or_raise(db, uuid.UUID(reconnect_id))
    else:
        connection = ProviderConnection(
            company_profile_id=uuid.UUID(decoded["company_profile_id"]),
            provider_key=provider_key,
        )
        db.add(connection)
        db.flush()

    connection.external_account_email = token_payload.external_account_email
    connection.scopes_granted = token_payload.scopes
    connection.status = ProviderConnectionStatus.CONNECTED
    connection.connected_at = _now()
    connection.disconnected_at = None
    # A fresh, successful code exchange IS a verification - no reason to
    # make the caller immediately call verify_connection() again just to
    # get last_verified_at populated.
    connection.last_verification_at = _now()
    connection.last_verified_at = _now()
    connection.last_verification_detail = None

    try:
        credential_store.save(
            db,
            connection.id,
            {
                "access_token": token_payload.access_token,
                "refresh_token": token_payload.refresh_token,
                "expires_at": token_payload.expires_at,
            },
        )
    except CredentialStoreError as exc:
        raise ConnectionError_(str(exc)) from exc
    db.commit()
    db.refresh(connection)
    return connection


def disconnect(db: Session, credential_store: CredentialStore, connection_id: uuid.UUID) -> ProviderConnection:
    connection = _get_connection_or_raise(db, connection_id)
    credential_store.delete(db, connection.id)
    connection.status = ProviderConnectionStatus.DISCONNECTED
    connection.disconnected_at = _now()
    db.commit()
    db.refresh(connection)
    return connection


def verify_connection(db: Session, credential_store: CredentialStore, connection_id: uuid.UUID) -> ProviderConnection:
    connection = _get_connection_or_raise(db, connection_id)
    connection.last_verification_at = _now()

    credential_payload = credential_store.load(db, connection.id)
    if credential_payload is None:
        connection.status = ProviderConnectionStatus.ERROR
        connection.last_verification_detail = "No credential is stored for this connection - reconnect required."
        db.commit()
        db.refresh(connection)
        return connection

    provider = get_provider(connection.provider_key)
    result = provider.verify(credential_payload)
    if result.success:
        connection.status = ProviderConnectionStatus.CONNECTED
        connection.last_verified_at = _now()
        connection.last_verification_detail = None
        if result.external_account_email:
            connection.external_account_email = result.external_account_email
    else:
        connection.status = ProviderConnectionStatus.ERROR
        connection.last_verification_detail = result.detail

    db.commit()
    db.refresh(connection)
    return connection


def refresh_credential_if_needed(
    db: Session, credential_store: CredentialStore, provider: EmailConnectionProvider, connection: ProviderConnection
) -> dict:
    """Called by dispatch_service before a send, not by the API layer -
    resolves a usable (non-expired) credential payload, transparently
    refreshing via the provider if the stored access_token has expired.
    Raises ConnectionError_ if there is no credential or no refresh_token
    to refresh with; the caller is responsible for flipping the
    connection's status in that case (see dispatch_service's docstring)."""
    payload = credential_store.load(db, connection.id)
    if payload is None:
        raise ConnectionError_(f"No credential stored for connection {connection.id}")

    expires_at = payload.get("expires_at")
    if expires_at is not None and expires_at > _now():
        return payload

    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise ConnectionError_(f"Credential for connection {connection.id} is expired and has no refresh_token")

    new_token = provider.refresh_access_token(refresh_token)
    new_payload = {
        "access_token": new_token.access_token,
        "refresh_token": new_token.refresh_token,
        "expires_at": new_token.expires_at,
    }
    credential_store.save(db, connection.id, new_payload)
    db.commit()
    return new_payload


def _get_connection_or_raise(db: Session, connection_id: uuid.UUID) -> ProviderConnection:
    connection = db.get(ProviderConnection, connection_id)
    if connection is None:
        raise ConnectionError_(f"ProviderConnection {connection_id} not found")
    return connection
