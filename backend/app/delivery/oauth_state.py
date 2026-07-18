"""
Signed encode/decode for the OAuth `state` payload - stdlib only (json,
base64, hmac, hashlib), deliberately kept in its own module with zero
sqlalchemy import so it's independently unit-testable without SQLAlchemy
installed, per the standing principle: modules with no database/HTTP/
OAuth/external dependency always get real executable unit tests. (The
functions here don't make any OAuth calls themselves - they just encode/
decode the opaque token carried through the redirect - so "OAuth" in the
module's name refers to what the payload is for, not an I/O dependency.)

WHY SIGNED (Layer 5 correction, not part of the original Layer 3 design):
Layer 3's version of this module produced a plain base64(json) token with
no integrity protection. That's not enough on its own even when paired
with an authenticated completion endpoint (see connection_service.py's
docstring) - an attacker can hand-craft an arbitrary state claiming any
company_profile_id, pair it with a code from their OWN legitimate OAuth
consent, and if the completing endpoint trusts state to select which
business to attach the connection to, an authenticated-but-unrelated
victim visiting a crafted link would end up with the attacker's mailbox
attached to the victim's business. Signing state with `secret` (the
caller passes app.core.config.settings.SECRET_KEY - never imported
directly here, so this module stays dependency-free) means a state can
only ever have been produced by encode_oauth_state itself, called from
an endpoint that already required the caller to own the
company_profile_id it encoded. An attacker who crafts their own state
either fails signature verification, or - if using a genuinely
backend-issued, correctly-signed state - can only ever get one
containing a company_profile_id THEY themselves owned at issuance time,
which defeats the cross-tenant attack. issued_at + max_age_seconds bounds
how long a leaked, validly-signed state/code pair remains replayable.

Used by connection_service.py, which owns everything that actually reads
or writes a ProviderConnection.
"""
import hashlib
import hmac
import json
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timezone

DEFAULT_MAX_AGE_SECONDS = 600  # 10 minutes - long enough for a real consent-screen interaction, short enough to bound replay


class OAuthStateError(Exception):
    """Raised when a `state` string can't be decoded, fails signature
    verification, or has expired. connection_service catches this and
    re-raises as its own ConnectionError_ so callers only need to handle
    one exception type from that module."""


def _sign(payload: dict, secret: str) -> str:
    body = json.dumps(payload, sort_keys=True)
    return hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


def encode_oauth_state(
    *, company_profile_id: uuid.UUID, provider_key: str, secret: str, reconnect_connection_id: uuid.UUID | None = None
) -> str:
    payload = {
        "company_profile_id": str(company_profile_id),
        "provider_key": provider_key,
        "reconnect_connection_id": str(reconnect_connection_id) if reconnect_connection_id else None,
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }
    envelope = {"payload": payload, "sig": _sign(payload, secret)}
    return urlsafe_b64encode(json.dumps(envelope).encode("utf-8")).decode("utf-8")


def decode_oauth_state(state: str, *, secret: str, max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS) -> dict:
    try:
        envelope = json.loads(urlsafe_b64decode(state.encode("utf-8")).decode("utf-8"))
        payload = envelope["payload"]
        signature = envelope["sig"]
    except Exception as exc:  # noqa: BLE001 - any malformed state is equally invalid
        raise OAuthStateError(f"Invalid OAuth state: {exc}") from exc

    if not hmac.compare_digest(signature, _sign(payload, secret)):
        raise OAuthStateError("OAuth state failed signature verification - it was tampered with, forged, or signed with a different secret.")

    try:
        issued_at = datetime.fromisoformat(payload["issued_at"])
    except (KeyError, ValueError) as exc:
        raise OAuthStateError(f"OAuth state is missing a valid issued_at: {exc}") from exc
    age_seconds = (datetime.now(timezone.utc) - issued_at).total_seconds()
    if age_seconds > max_age_seconds:
        raise OAuthStateError(f"OAuth state has expired ({age_seconds:.0f}s old, max {max_age_seconds}s) - please restart the connect/reconnect flow.")
    if age_seconds < -30:  # small negative tolerance for clock skew between processes
        raise OAuthStateError("OAuth state's issued_at is in the future - rejecting as invalid.")

    return payload
