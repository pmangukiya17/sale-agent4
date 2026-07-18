"""
The only CredentialStore implemented in M5: encrypts the payload with
Fernet (symmetric, authenticated encryption from the `cryptography`
library) and stores the ciphertext directly in
provider_credentials.encrypted_payload. secret_ref stays null for this
backend - see ProviderCredential's docstring for the two-shape design.

Deliberately not a caching layer and not a singleton - a fresh
Fernet(key) is cheap to construct, and holding the key only for the
duration of one save()/load()/delete() call (never as a long-lived
instance attribute anyone else could accidentally read) is a small,
free hardening step for something this sensitive.
"""
import uuid
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.delivery.credentials.base import CredentialStore, CredentialStoreError
from app.delivery.credentials.payload_codec import deserialize_payload, serialize_payload
from app.models.provider_credential import ProviderCredential


def _get_fernet() -> Fernet:
    key = settings.CREDENTIAL_ENCRYPTION_KEY
    if not key:
        # Fails loudly the first time credential code actually runs, not
        # at app import time - see core/config.py's comment on this
        # setting for why there's no default.
        raise CredentialStoreError(
            "CREDENTIAL_ENCRYPTION_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
            "and set it in .env before connecting any provider."
        )
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise CredentialStoreError(f"CREDENTIAL_ENCRYPTION_KEY is not a valid Fernet key: {exc}") from exc


class PostgresFernetCredentialStore(CredentialStore):
    backend_key = "postgres_fernet"

    def save(self, db: Session, provider_connection_id: uuid.UUID, payload: dict) -> None:
        fernet = _get_fernet()
        ciphertext = fernet.encrypt(serialize_payload(payload).encode("utf-8")).decode("utf-8")

        existing = db.scalars(
            select(ProviderCredential).where(ProviderCredential.provider_connection_id == provider_connection_id)
        ).first()
        if existing is not None:
            existing.encrypted_payload = ciphertext
            existing.backend = self.backend_key
            existing.rotated_at = datetime.now(timezone.utc)
        else:
            db.add(
                ProviderCredential(
                    provider_connection_id=provider_connection_id,
                    backend=self.backend_key,
                    encrypted_payload=ciphertext,
                )
            )
        db.flush()

    def load(self, db: Session, provider_connection_id: uuid.UUID) -> dict | None:
        credential = db.scalars(
            select(ProviderCredential).where(ProviderCredential.provider_connection_id == provider_connection_id)
        ).first()
        if credential is None or credential.encrypted_payload is None:
            return None
        fernet = _get_fernet()
        try:
            plaintext = fernet.decrypt(credential.encrypted_payload.encode("utf-8"))
        except InvalidToken as exc:
            # Wrong/rotated CREDENTIAL_ENCRYPTION_KEY, or corrupted data -
            # either way this is a genuine failure the caller must not
            # silently swallow (it would otherwise look like "no
            # credential", which is a different, benign case).
            raise CredentialStoreError(
                f"Could not decrypt stored credential for connection {provider_connection_id} "
                "- CREDENTIAL_ENCRYPTION_KEY may have changed since this credential was saved."
            ) from exc
        return deserialize_payload(plaintext.decode("utf-8"))

    def delete(self, db: Session, provider_connection_id: uuid.UUID) -> None:
        existing = db.scalars(
            select(ProviderCredential).where(ProviderCredential.provider_connection_id == provider_connection_id)
        ).first()
        if existing is not None:
            db.delete(existing)
            db.flush()
