"""
Pure serialization for credential payloads - stdlib only (json, datetime),
deliberately kept in its own module with zero sqlalchemy/cryptography
imports so it's independently unit-testable without either installed, per
the standing principle: modules with no database/HTTP/OAuth/external
dependency always get real executable unit tests. Used by
postgres_fernet_store.py (and, if a Vault/Secrets Manager backend is
added later, whichever CredentialStore that becomes too - this module has
no opinion on where the resulting string ends up stored).
"""
import json
from datetime import datetime


def serialize_payload(payload: dict) -> str:
    """datetime isn't JSON-serializable by default - expires_at is the
    only field expected to carry one, but this handles any datetime value
    defensively rather than assuming the exact payload shape."""

    def _default(value):
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    return json.dumps(payload, default=_default)


def deserialize_payload(raw: str) -> dict:
    data = json.loads(raw)
    if data.get("expires_at"):
        data["expires_at"] = datetime.fromisoformat(data["expires_at"])
    return data
