"""
CredentialStore registry. Same plugin-registry pattern as every other one
in this codebase, selected by app-level setting rather than per-connection
- M5 has exactly one backend active at a time. Swapping to Vault/Key
Vault/Secrets Manager later is a new class here + changing
CREDENTIAL_STORE_BACKEND, never a change to any caller of
get_credential_store().
"""
from app.core.config import settings
from app.delivery.credentials.base import CredentialStore
from app.delivery.credentials.postgres_fernet_store import PostgresFernetCredentialStore

CREDENTIAL_STORE_REGISTRY: dict[str, type[CredentialStore]] = {
    PostgresFernetCredentialStore.backend_key: PostgresFernetCredentialStore,
}


def get_credential_store() -> CredentialStore:
    backend_key = settings.CREDENTIAL_STORE_BACKEND
    store_cls = CREDENTIAL_STORE_REGISTRY.get(backend_key)
    if store_cls is None:
        raise KeyError(f"Unknown credential store backend '{backend_key}'. Registered: {list(CREDENTIAL_STORE_REGISTRY)}")
    return store_cls()
