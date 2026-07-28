import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AIProviderConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    M8.3 (AI Gateway Management & Control, Step 1). One row per AI Gateway
    provider_key (local_ollama/groq/gemini_ai_studio/gemini/claude/openai) -
    an OPTIONAL, DB-backed override sitting in front of the `.env`-sourced
    `app.core.config.settings` values every `ProviderClient` read directly
    before this milestone. A provider_key with NO row here behaves exactly
    as it did pre-M8.3 - settings-only, zero change - this table is
    additive and every field genuinely optional (except `provider_key`/
    `enabled` themselves) by design, never a hard requirement to configure
    every provider through the UI.

    Read exclusively through `app.ai_gateway.provider_config.resolve_provider_config()`
    - never queried directly by a `ProviderClient` - see that module's own
    docstring for why: a resolver function, not a raw model read, is what
    lets `enabled`/`base_url`/`default_model`/`api_key` each independently
    fall back to their own settings-sourced value when unset here, and is
    what enforces "always a fresh read, no caching" (CEO requirement -
    runtime config changes must take effect immediately, no restart).

    `enabled` defaults True and is meaningful ONLY once a row exists - it
    is the one field that can't simply "fall back" to a settings value
    (there is no `settings.<PROVIDER>_ENABLED` today); an operator
    explicitly saving `enabled=False` is how Provider Management's
    "Disable" action works, distinct from clearing credentials.

    `encrypted_api_key` reuses the EXACT SAME encryption primitive already
    used for mailbox OAuth credentials - `cryptography.fernet.Fernet` keyed
    by `settings.CREDENTIAL_ENCRYPTION_KEY` (see
    `app/delivery/credentials/postgres_fernet_store.py`'s own `_get_fernet()`
    for the precedent this mirrors) - NOT the `app.delivery.credentials`
    `CredentialStore` abstraction itself, which is keyed by
    `provider_connection_id` and shaped for an OAuth token payload dict; an
    AI provider credential is a single static string, a genuinely different
    shape, so this gets its own small encrypt/decrypt pair in
    `provider_config.py` rather than forcing a mismatched reuse. Never
    logged, never returned decrypted by any read API, never written to
    `AIProviderConfigAudit.field_changes` in plaintext - see that model's
    own docstring.

    `base_url`/`default_model` mirror exactly what every `ProviderClient`
    already exposes as its own `base_url`/`default_model` property -
    generic, provider-agnostic columns because literally every provider
    this codebase has ever registered uses both concepts.

    `extra_settings` (JSONB, default `{}`) is the deliberate escape hatch
    the CEO's own refinement asked for: "the schema should allow future
    provider-specific settings without redesigning the architecture." A
    provider whose configuration surface is genuinely more than API
    key/base URL/default model (a region, an organization id, a deployment
    name, sampling defaults, ...) gets a new key in this dict, read by
    that provider's own client code via
    `resolve_provider_config(...).extra_settings.get(...)` - never a new
    migration, mirroring the same "escape hatch" JSONB convention already
    established elsewhere in this codebase (`OutreachJob.log`,
    `DeliveryEvent.detail`, `MailboxBrief.recommendations`/`statistics`).

    `updated_by_user_id` is a convenience pointer to "who last touched
    this provider's config" without joining `AIProviderConfigAudit` - the
    audit table remains the authoritative CHANGE HISTORY (every change,
    field-by-field); this column is only ever the most recent value.
    `ondelete="SET NULL"` - a provider's configuration must survive the
    user who last edited it being deleted, exactly the same reasoning
    `AIRequestLog.company_profile_id`/`Notification.company_profile_id`
    already established for "historical/operational record outlives its
    referenced actor."
    """

    __tablename__ = "ai_provider_configs"

    provider_key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    extra_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    updated_by_user: Mapped["User | None"] = relationship()
