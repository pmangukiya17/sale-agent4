import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProviderCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    The actual secret material for one ProviderConnection, deliberately
    split into its own table/model rather than columns on
    ProviderConnection - this IS the credential-storage abstraction
    requested for M5: swapping from Postgres+Fernet to Vault/Azure Key
    Vault/AWS Secrets Manager later means writing a new
    app.delivery.credentials.base.CredentialStore implementation and
    changing which one is wired in (app.delivery.credentials.registry), not
    touching ProviderConnection's shape at all - it never had secret
    columns to begin with.

    backend is a plain string (not an enum), same extensibility reasoning
    as provider_key: "postgres_fernet" today; "vault"/"aws_secrets_manager"/
    "azure_key_vault" later are a new CredentialStore class + registry
    entry, never a migration.

    Two storage shapes coexist by design, selected by `backend`:
    - Local (postgres_fernet): encrypted_payload holds the Fernet-encrypted
      JSON blob ({access_token, refresh_token, expires_at}) directly in
      this row; secret_ref is unused (null).
    - External (vault/aws_secrets_manager/azure_key_vault): secret_ref
      holds that backend's own locator (a Vault path, a Secrets Manager
      ARN, a Key Vault URI); encrypted_payload is unused (null) because the
      actual secret never touches this database at all.

    provider_connection_id is unique - one credential per connection today
    - modeled as its own table specifically so that constraint is a data
    fact, not a structural one; it could be relaxed later (e.g. a
    multi-part secret) without redesigning ProviderConnection.
    """

    __tablename__ = "provider_credentials"

    provider_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("provider_connections.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    backend: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    secret_ref: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    encrypted_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(nullable=True)

    provider_connection: Mapped["ProviderConnection"] = relationship(back_populates="credential")
