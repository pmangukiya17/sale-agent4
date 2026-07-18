"""
CredentialStore: the abstraction that makes swapping from Postgres+Fernet
to Vault/Azure Key Vault/AWS Secrets Manager later a new class + a
registry entry, never a ProviderConnection redesign - see
ProviderCredential's model docstring. A store's job is only to persist and
retrieve a plain dict payload keyed by provider_connection_id; it has no
opinion on what that payload contains (that's OAuthTokenPayload, defined
in providers/base.py) or how it's obtained (that's the provider's job).
"""
from abc import ABC, abstractmethod
from typing import ClassVar
import uuid

from sqlalchemy.orm import Session


class CredentialStoreError(Exception):
    """Raised for a genuine storage failure (key missing, decryption
    failed, backend unreachable) - never for "no credential exists yet",
    which callers should check for via load() returning None instead."""


class CredentialStore(ABC):
    backend_key: ClassVar[str]

    @abstractmethod
    def save(self, db: Session, provider_connection_id: uuid.UUID, payload: dict) -> None:
        """Persists payload (access_token/refresh_token/expires_at/...)
        for this connection. Creates the ProviderCredential row if none
        exists yet, otherwise overwrites it (this is `rotate` too - a
        fresh save IS a rotation; there is no separate rotate() method,
        since "save when one already exists" and "rotate" are the same
        operation from the store's point of view)."""
        raise NotImplementedError

    @abstractmethod
    def load(self, db: Session, provider_connection_id: uuid.UUID) -> dict | None:
        """Returns the decrypted payload, or None if this connection has
        no stored credential (e.g. never connected, or disconnected)."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, db: Session, provider_connection_id: uuid.UUID) -> None:
        """Removes the stored credential. Called by Disconnect. Must be
        safe to call when no credential exists (no-op, not an error)."""
        raise NotImplementedError
