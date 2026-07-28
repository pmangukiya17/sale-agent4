"""
local_model_policy.py - Task-based local-model selection (M8.2 addendum,
approved 2026-07-28; extended M8.3 Step 3 - Model Role Management,
approved 2026-07-28). The single centralized place inside the AI Gateway
that decides WHICH locally-hosted model `LocalOllamaProviderClient` should
ask Ollama (or any OpenAI-compatible local server) for, based on
`GatewayRequest.capability` - a strictly provider-internal concern, never
visible to `ProviderRouter`/`RoutingDecision`. Router.py's own principle
is unextended and unchanged by this file: the router decides WHICH
provider_key to try (local/free/premium), never which model a given
provider_key uses internally - see router.py's own docstring. Model
selection has always been a per-provider concern (`default_model` is
already a per-ProviderClient property); this module only makes that
existing concern capability-aware for exactly one provider.

Three-level indirection - capability -> ordered semantic ROLE preference
-> resolved model string - never capability -> model directly, and
deliberately NOT positional ("default"/"secondary") naming. A role name
describes WHAT KIND of task the model is being asked to do ("research",
"writing", and, as this table grows, "coding"/"vision"/"reasoning"/
"embeddings"...), so a future third or fourth local model slots in as a
new role without ever renaming an existing one - the exact failure mode
positional naming ("tertiary", "quaternary"...) would eventually hit.

This is the same shape every other policy table in this package already
uses: `router.CAPABILITY_PROVIDER_PREFERENCE` is capability -> ordered
provider_key preference; `tiers.PROVIDER_TIER_REGISTRY` is provider_key ->
tier; `accounting`'s price table is (provider_key, model) -> price. This is
capability -> ordered semantic-role preference -> resolved model. Nothing
here is a new pattern.

`CAPABILITY_LOCAL_MODEL_ROLE` (capability -> ordered role preference)
stays a CODE-level table, unchanged by Step 3 - which capability prefers
which role is a business-logic/routing decision, the same category as
`router.py`'s own `CAPABILITY_PROVIDER_PREFERENCE`, not something Step 3's
editor UI exposes for editing.

`LOCAL_MODEL_ROLES` (role name -> SETTINGS attribute name, not a resolved
value) is now the FALLBACK layer only, as of Step 3 - see
`resolve_local_model()`'s own docstring for the resolution order. It
remains exactly as it was pre-Step-3: any deployment that never touches
the new `ai_model_roles` table (via `save_model_role()`/the editor UI)
behaves identically to before this migration.

Step 3's new DB-backed layer (`app.models.ai_model_role.AIModelRole`,
read via `_resolve_db_model_for_role()` below) is what actually lets an
admin add Coding/Vision/Reasoning/Embeddings as NEW ROWS, with no new
settings key and no code deploy - the CEO's own "future models addable
without business-logic changes" requirement, now satisfied for role ->
model assignment specifically (it was already true one level up, for
capability -> role preference, since that's always been data in a dict
literal here). Per CEO decision #2 (Section 12 of
docs/architecture/m8-3-ai-gateway-control-center-plan.md): semantic roles
stay LOCAL-TIER ONLY - this module (and the table underneath it) is read
exclusively by `LocalOllamaProviderClient._resolve_model()`. No cloud
`ProviderClient` is touched by Step 3.

Extending this for the future, post-Step-3, is now just ONE additive
edit, not two:
  1. Through the editor UI (or `save_model_role()` directly), save a new
     `role_name` -> `model` row - e.g. `role_name="coding"`,
     `model="codellama:13b"`.
  2. Add one `"<role_name>"` entry to whichever capability's preference
     list in `CAPABILITY_LOCAL_MODEL_ROLE` should use it (still a code
     change - see above for why that stays code, not data).
The old `.env`-only path (add a `LOCAL_MODEL_<NAME>_MODEL` setting + a
`LOCAL_MODEL_ROLES` entry) still works unchanged as the fallback route,
for anyone who prefers config-file-only deployment over the DB editor.

Disclosed scope note (unchanged from M8.2): `CAPABILITY_LOCAL_MODEL_ROLE`
includes two entries ("buyer_discovery", "crm_data_extraction") that are
NOT live `GatewayRequest.capability` traffic yet - neither `app/discovery`
nor `app/crm_automation` calls the AI Gateway today. These are
forward-looking, inert placeholders - safe to declare ahead of use. The
two capabilities genuinely live today are `"research_analysis"`
(Research's `LLMAnalysisEngine`) and `"outreach_email_generation"`
(Outreach's LLM email channel).
"""
import logging

logger = logging.getLogger("app.ai_gateway.local_model_policy")

# role name -> settings attribute name (never the resolved value itself -
# see module docstring for why this stays a lazy lookup). Semantic, not
# positional - see module docstring for why that distinction matters long
# term. As of Step 3 this is the FALLBACK consulted only when no
# `ai_model_roles` DB row exists for a given role name (see
# `resolve_local_model()`).
LOCAL_MODEL_ROLES: dict[str, str] = {
    "research": "LOCAL_MODEL_DEFAULT_MODEL",
    "writing": "LOCAL_MODEL_SECONDARY_MODEL",
}

# capability -> ordered role preference (most-preferred role first, same
# "ordered list, first configured wins" shape router.py's own
# CAPABILITY_PROVIDER_PREFERENCE already uses one level up). A capability
# absent from this dict falls back to _FALLBACK_ROLE_PREFERENCE - same
# "must always resolve to something" convention
# CAPABILITY_PROVIDER_PREFERENCE's own `_DEFAULT_CAPABILITY_KEY` entry
# already established. Stays a code-level table - see module docstring.
#
# "outreach_email_generation" prefers "writing" (e.g. llama3.1:8b) and
# falls back to "research" (e.g. qwen3:8b) if the writing role isn't
# configured - this is what delivers "prefer llama3.1:8b, fall back to
# qwen3:8b if unavailable" without ever hardcoding either model name here.
CAPABILITY_LOCAL_MODEL_ROLE: dict[str, list[str]] = {
    "research_analysis": ["research"],
    "outreach_email_generation": ["writing", "research"],
    # Not yet live traffic - see module docstring's disclosed scope note.
    "buyer_discovery": ["research"],
    "crm_data_extraction": ["research"],
}
_FALLBACK_ROLE_PREFERENCE = ["research"]


def _resolve_db_model_for_role(role_name: str) -> str | None:
    """Real, production DB lookup for one role's DB-backed override -
    always a FRESH read, no caching anywhere, same "runtime change takes
    effect immediately, no restart" discipline
    `provider_config.resolve_provider_config()` already established for
    Step 1. Opens and closes its own short-lived `SessionLocal()` (same
    convention as that function). Returns `None` (never raises) for: no
    row for this role_name, a row that's `enabled=False`, a row with an
    empty `model`, or the DB/sqlalchemy genuinely being unavailable
    (this project's own sandbox constraint - see
    `tests/test_provider_config_pure.py`'s own disclosure for the
    identical failure mode) - every one of these is "fail open to the
    settings-based fallback," never a hard error that would take down
    local model resolution over a config-lookup hiccup."""
    try:
        from app.db.session import SessionLocal
        from app.models.ai_model_role import AIModelRole
    except Exception:  # noqa: BLE001 - sqlalchemy/pydantic_settings genuinely absent in some environments
        return None

    db = SessionLocal()
    try:
        row = (
            db.query(AIModelRole)
            .filter(AIModelRole.role_name == role_name, AIModelRole.enabled.is_(True))
            .first()
        )
    except Exception:  # noqa: BLE001 - DB down, migration not yet applied, etc. - fail OPEN
        logger.warning("ai_gateway.model_role_resolve_failed", exc_info=True)
        row = None
    finally:
        db.close()

    return row.model if row is not None and row.model else None


def resolve_local_model(capability: str, *, settings_obj=None, db_lookup=None) -> str | None:
    """Walks `capability`'s role preference list (or the fallback, for an
    unlisted capability). For EACH role in the list, in order: first
    checks the DB-backed override via `db_lookup` (Step 3's
    `ai_model_roles` table) - if a row exists, is enabled, and has a
    non-empty `model`, that value wins immediately, without even looking
    at `LOCAL_MODEL_ROLES`/settings for that role. Only if no DB override
    exists for that role does this fall through to the pre-Step-3 behavior
    (`LOCAL_MODEL_ROLES`'s settings-attribute indirection). An
    unrecognized role name in the preference list (a data bug in this
    table, not a runtime condition) is likewise just skipped, never
    raised - this function must never throw, since its one caller
    (`LocalOllamaProviderClient._resolve_model()`) already has a safe
    final fallback (`self.default_model`) it can use if this returns
    None.

    `settings_obj` is a deliberate testability seam, same convention as
    `AIGateway`'s own `provider_lookup` constructor param and
    `SearchService`'s own DI seam - both documented there for the
    identical reason: this project's test sandbox has neither
    `pydantic_settings` nor `sqlalchemy` installed, so any test that
    imports the real `app.core.config.settings` cannot run as a "pure"
    test. Passing any object with the relevant `LOCAL_MODEL_*_MODEL`
    attributes set lets `tests/test_local_model_policy_pure.py` exercise
    this function's settings-fallback branching with zero third-party
    dependencies. Production code never passes this - the default
    (`None`) triggers the real, lazy `app.core.config.settings` import.

    `db_lookup` is the SAME seam pattern, one level up: a callable
    `(role_name: str) -> str | None`. Defaults to the real
    `_resolve_db_model_for_role` (a genuine DB read) in production.
    `tests/test_local_model_policy_pure.py` passes a plain dict-backed
    fake to exercise "DB override wins over settings," "disabled/absent
    DB row falls through to settings," and "role unrecognized by either
    layer is skipped" - all real branching logic in THIS function,
    without needing a real Postgres connection. The real DB-round-trip
    path (a genuine `ai_model_roles` row actually overriding a real
    settings-configured role) is covered by
    `tests/test_model_role_management_e2e.py` instead, same division of
    labor Step 1 already established between `test_provider_config_pure.py`
    and `test_provider_config_e2e.py`."""
    if db_lookup is None:
        db_lookup = _resolve_db_model_for_role
    if settings_obj is None:
        from app.core.config import settings as settings_obj  # lazy - see module docstring

    for role in CAPABILITY_LOCAL_MODEL_ROLE.get(capability, _FALLBACK_ROLE_PREFERENCE):
        db_value = db_lookup(role)
        if db_value:
            return db_value

        attr = LOCAL_MODEL_ROLES.get(role)
        if attr is None:
            continue
        value = getattr(settings_obj, attr, None)
        if value:
            return value
    return None


def list_model_roles(db):
    """Returns every `AIModelRole` row, ordered by `role_name` - the read
    side of Step 3's editor UI. Includes disabled rows (the UI needs to
    show and let an admin re-enable them, not just hide them)."""
    from app.models.ai_model_role import AIModelRole

    return db.query(AIModelRole).order_by(AIModelRole.role_name.asc()).all()


def save_model_role(db, role_name: str, *, model: str | None = None, enabled: bool | None = None, changed_by_user_id=None):
    """Creates or updates the one `AIModelRole` row for `role_name`. Every
    parameter left as `None` (the default) means "leave this field
    alone," same "explicit means something, absent means unchanged"
    convention `provider_config.save_provider_config()` already
    established. No audit table this step (see `AIModelRole`'s own
    docstring for why) - `updated_by_user_id`/`updated_at` are the only
    "who/when" record kept.

    A brand-new `role_name` requires `model` to be provided (there is no
    sensible "create an empty role" - `AIModelRole.model` is
    non-nullable) - raises `ValueError` otherwise, a caller-side
    programming error, not a runtime condition worth failing open over."""
    from app.models.ai_model_role import AIModelRole

    row = db.query(AIModelRole).filter(AIModelRole.role_name == role_name).first()
    if row is None:
        if not model:
            raise ValueError(f"Cannot create model role '{role_name}' without a `model` value.")
        row = AIModelRole(role_name=role_name, model=model, enabled=enabled if enabled is not None else True)
        db.add(row)
        db.flush()
    else:
        if model is not None:
            row.model = model
        if enabled is not None:
            row.enabled = enabled

    if changed_by_user_id is not None:
        row.updated_by_user_id = changed_by_user_id

    db.flush()
    return row


def delete_model_role(db, role_name: str) -> bool:
    """Deletes the `AIModelRole` row for `role_name`, if one exists.
    Returns whether a row was actually deleted. A role with no DB row
    simply resolves via the `LOCAL_MODEL_ROLES` settings fallback again -
    deleting is a safe, reversible-by-recreating operation, never a data
    -loss risk for anything this table doesn't itself own."""
    from app.models.ai_model_role import AIModelRole

    row = db.query(AIModelRole).filter(AIModelRole.role_name == role_name).first()
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True
