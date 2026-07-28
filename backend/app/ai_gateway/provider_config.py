"""
provider_config.py - M8.3 (AI Gateway Management & Control, Step 1). The
single centralized place a provider's EFFECTIVE configuration is resolved
- CEO-approved design (see docs/architecture/m8-3-ai-gateway-control-center-plan.md
Section 12): a DB-backed override (`app.models.ai_provider_config.AIProviderConfig`),
read completely fresh on EVERY call - no caching anywhere, not even
request-scoped - merged over the settings-based fallback values the
calling `ProviderClient` already knows how to compute for itself.

Why "no caching at all" rather than the request-scoped caching the CEO
offered as an alternative: this table has at most a handful of rows (one
per registered provider_key) and is read at most a few times per single
`complete()` call - the cost of always querying fresh is negligible, and
it trivially satisfies "a runtime configuration change must become
effective immediately, with no backend restart" without needing any cache
invalidation logic to get right. Simplicity over a micro-optimization
that would add its own correctness risk for no measurable benefit.

Why the CALLER supplies its own fallback values (`fallback_api_key=...`)
instead of this module knowing "ANTHROPIC_API_KEY belongs to claude" for
every provider_key: hardcoding that mapping here would violate the exact
provider-neutral discipline every other AI Gateway module upholds
(`router.py`/`tiers.py`/`capabilities.py` never know which settings
attribute belongs to which provider_key either), and would mean every
future provider needs a new branch in THIS file - directly contradicting
M-AIGW-2's own "adding a provider is additive, never touches a shared
if/elif ladder" checklist. Each `ProviderClient` already reads its own
`settings.<PROVIDER>_API_KEY`/`_BASE_URL`/`_DEFAULT_MODEL` - it passes
those through as fallbacks, and this module's only job is "override with
a DB value if one was explicitly saved."

`extra_settings` is the CEO's explicit extensibility requirement: a
provider whose configuration surface is genuinely more than API key/base
URL/default model gets a new key in this dict (set via
`save_provider_config(..., extra_settings={...})`), read by that
provider's own client code directly off the resolved
`ResolvedProviderConfig.extra_settings` - never a new column, never a new
migration, never a change to this module's own function signature.

Failure mode, disclosed and deliberate: if the DB is unreachable, this
migration hasn't been applied yet, or sqlalchemy/pydantic_settings aren't
importable (this project's own sandbox constraint - see
tests/test_provider_config_pure.py's own disclosure),
`resolve_provider_config()` FAILS OPEN to the given fallback values,
exactly as if no override row existed - it never raises, and never breaks
a real Gateway call over a config-lookup hiccup. This mirrors
`app.ai_gateway.request_log`'s own "observability must never be
load-bearing" discipline, applied here to configuration resolution
specifically: a transient DB blip degrades a deployment back to its
pre-M8.3, settings-only behavior for that one call, never to a hard
failure that would take down every provider at once over a single
missing table.
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("app.ai_gateway.provider_config")


@dataclass(frozen=True)
class ResolvedProviderConfig:
    """The fully-merged, EFFECTIVE configuration for one provider_key -
    what a `ProviderClient` should actually use right now. Never
    constructed directly by a caller outside this module."""

    enabled: bool
    api_key: str | None
    base_url: str | None
    default_model: str | None
    extra_settings: dict = field(default_factory=dict)


def _get_fernet(settings_obj=None):
    """Returns a Fernet instance keyed by the SAME
    `settings.CREDENTIAL_ENCRYPTION_KEY` already used for mailbox OAuth
    credential storage (`app/delivery/credentials/postgres_fernet_store.py`'s
    own `_get_fernet()`) - deliberately the same key/mechanism, not a
    second encryption scheme for AI provider secrets specifically. Returns
    None (never raises) if the key is unset or invalid - callers decide
    what that means for their own operation (encrypt: a real error the
    save must surface; decrypt: a safe, logged no-op).

    `settings_obj` is a DI seam, same convention
    `app.ai_gateway.local_model_policy.resolve_local_model()` already
    established - lets `tests/test_provider_config_pure.py` exercise the
    real encrypt/decrypt round trip (genuinely, via the real
    `cryptography` package, which IS installed in this project's sandbox
    - unlike sqlalchemy/pydantic_settings) without needing
    `app.core.config.settings` constructible."""
    from cryptography.fernet import Fernet

    if settings_obj is None:
        from app.core.config import settings as settings_obj

    key = settings_obj.CREDENTIAL_ENCRYPTION_KEY
    if not key:
        return None
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except (ValueError, TypeError):
        return None


def _encrypt_api_key(plaintext: str | None, *, settings_obj=None) -> str | None:
    if not plaintext:
        return None
    fernet = _get_fernet(settings_obj)
    if fernet is None:
        raise ValueError(
            "CREDENTIAL_ENCRYPTION_KEY is not set (or is not a valid Fernet key) - cannot store an AI provider "
            "API key. Generate one with `python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())"` and set it in .env before saving provider credentials.'
        )
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def _decrypt_api_key(ciphertext: str | None, *, settings_obj=None) -> str | None:
    if not ciphertext:
        return None
    fernet = _get_fernet(settings_obj)
    if fernet is None:
        logger.warning("ai_gateway.provider_config_decrypt_skipped", extra={"reason": "encryption_key_unset_or_invalid"})
        return None
    from cryptography.fernet import InvalidToken

    try:
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Wrong/rotated CREDENTIAL_ENCRYPTION_KEY, or corrupted data - same
        # "fail open to no-override" direction as a DB-unavailable failure
        # (see module docstring), not a raised exception - a stored
        # override this process can no longer decrypt should degrade to
        # "as if unset," never take the whole provider down.
        logger.warning("ai_gateway.provider_config_decrypt_failed")
        return None


def resolve_provider_config(
    provider_key: str,
    *,
    fallback_enabled: bool = True,
    fallback_api_key: str | None = None,
    fallback_base_url: str | None = None,
    fallback_default_model: str | None = None,
) -> ResolvedProviderConfig:
    """Always a FRESH DB read - see module docstring for why no caching,
    at any scope, is used. Opens and closes its own short-lived
    `SessionLocal()` (the same "worker opens its own session" convention
    `app.ai_gateway.request_log._persist_ai_request_log()` and every
    background worker in this codebase already use) - never threads a
    `Session` through `ProviderClient`'s public interface, which stays
    DB-free by design; every existing caller of `is_configured()`/
    `default_model`/`complete()` is unaffected by this function's own
    internals.

    `fallback_*` are the values the calling `ProviderClient` already
    computed from `app.core.config.settings` - each independently
    overridden only if a DB row exists AND that specific field was
    actually set on it, never an all-or-nothing swap."""
    try:
        from app.db.session import SessionLocal
        from app.models.ai_provider_config import AIProviderConfig
    except Exception:  # noqa: BLE001 - sqlalchemy/pydantic_settings genuinely absent in some environments
        return ResolvedProviderConfig(
            enabled=fallback_enabled,
            api_key=fallback_api_key,
            base_url=fallback_base_url,
            default_model=fallback_default_model,
        )

    row = None
    db = SessionLocal()
    try:
        row = db.query(AIProviderConfig).filter(AIProviderConfig.provider_key == provider_key).first()
    except Exception:  # noqa: BLE001 - DB down, migration not yet applied, etc. - fail OPEN, see module docstring
        logger.warning("ai_gateway.provider_config_resolve_failed", exc_info=True)
        row = None
    finally:
        db.close()

    if row is None:
        return ResolvedProviderConfig(
            enabled=fallback_enabled,
            api_key=fallback_api_key,
            base_url=fallback_base_url,
            default_model=fallback_default_model,
        )

    return ResolvedProviderConfig(
        enabled=row.enabled,
        api_key=_decrypt_api_key(row.encrypted_api_key) or fallback_api_key,
        base_url=row.base_url or fallback_base_url,
        default_model=row.default_model or fallback_default_model,
        extra_settings=dict(row.extra_settings or {}),
    )


def save_provider_config(
    db,
    provider_key: str,
    *,
    changed_by_user_id=None,
    enabled: bool | None = None,
    api_key: str | None = None,
    clear_api_key: bool = False,
    base_url: str | None = None,
    clear_base_url: bool = False,
    default_model: str | None = None,
    clear_default_model: bool = False,
    extra_settings: dict | None = None,
):
    """Creates or updates the one `AIProviderConfig` row for `provider_key`
    and writes AT MOST ONE `AIProviderConfigAudit` row describing exactly
    which fields changed in this call - never one audit row per field,
    and NO audit row at all if nothing actually changed (the CEO's own
    "record what fields changed" requirement, read literally: a save that
    changes nothing has nothing to record).

    Every parameter left as `None` (the default) means "leave this field
    alone." The explicit `clear_api_key`/`clear_base_url`/
    `clear_default_model` booleans exist because `None` is itself a
    meaningful value for those three fields (clearing a stored override
    back to "defer to settings.<X>") - without them, a bare `api_key=None`
    on every call that isn't touching credentials would be ambiguous
    between "leave alone" and "clear."

    NEVER records a plaintext `api_key` value in `field_changes` - only a
    `"unset"`/`"set"` marker for that one field (see
    `AIProviderConfigAudit`'s own docstring). Every other field's real
    old/new value is recorded, since knowing exactly what changed is this
    table's entire purpose for those.

    This function is intentionally callable and tested now, in Step 1,
    even though no HTTP route calls it yet (that's Step 2's Provider
    Management endpoint) - the CEO's Step 1 scope explicitly includes
    "encrypted credential storage," and building the write path (with its
    audit trail) alongside the read path this milestone, rather than
    leaving it untested until Step 2 wires an endpoint to it, is the
    safer order for something this security-sensitive."""
    from datetime import datetime, timezone

    from app.models.ai_provider_config import AIProviderConfig
    from app.models.ai_provider_config_audit import AIProviderConfigAudit

    row = db.query(AIProviderConfig).filter(AIProviderConfig.provider_key == provider_key).first()
    if row is None:
        row = AIProviderConfig(provider_key=provider_key, enabled=True, extra_settings={})
        db.add(row)
        db.flush()

    field_changes: dict = {}

    if enabled is not None and enabled != row.enabled:
        field_changes["enabled"] = {"old": row.enabled, "new": enabled}
        row.enabled = enabled

    if clear_api_key:
        if row.encrypted_api_key is not None:
            field_changes["api_key"] = {"old": "set", "new": "unset"}
        row.encrypted_api_key = None
    elif api_key is not None:
        had_key = row.encrypted_api_key is not None
        row.encrypted_api_key = _encrypt_api_key(api_key)
        field_changes["api_key"] = {"old": "set" if had_key else "unset", "new": "set"}

    if clear_base_url:
        if row.base_url is not None:
            field_changes["base_url"] = {"old": row.base_url, "new": None}
        row.base_url = None
    elif base_url is not None and base_url != row.base_url:
        field_changes["base_url"] = {"old": row.base_url, "new": base_url}
        row.base_url = base_url

    if clear_default_model:
        if row.default_model is not None:
            field_changes["default_model"] = {"old": row.default_model, "new": None}
        row.default_model = None
    elif default_model is not None and default_model != row.default_model:
        field_changes["default_model"] = {"old": row.default_model, "new": default_model}
        row.default_model = default_model

    if extra_settings is not None and extra_settings != (row.extra_settings or {}):
        field_changes["extra_settings"] = {"old": row.extra_settings or {}, "new": extra_settings}
        row.extra_settings = extra_settings

    if changed_by_user_id is not None:
        row.updated_by_user_id = changed_by_user_id

    db.flush()

    if field_changes:
        db.add(
            AIProviderConfigAudit(
                provider_key=provider_key,
                changed_at=datetime.now(timezone.utc),
                changed_by_user_id=changed_by_user_id,
                field_changes=field_changes,
            )
        )
        db.flush()

    return row
