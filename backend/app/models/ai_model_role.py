import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AIModelRole(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    M8.3 (AI Gateway Management & Control, Step 3 - Model Role Management).
    One row per SEMANTIC ROLE NAME ("research"/"writing"/"coding"/"vision"/
    "reasoning"/"embeddings"/...) - a DB-backed override sitting in front of
    the hardcoded `LOCAL_MODEL_ROLES` dict in
    `app.ai_gateway.local_model_policy`, exactly the same "optional DB
    override, settings/code fallback, zero change until an operator
    explicitly saves something" shape `AIProviderConfig` (Step 1) already
    established for provider-level config. A role name with NO row here
    resolves exactly as it did pre-Step-3 - via `LOCAL_MODEL_ROLES`'s
    settings-attribute indirection - so this table is additive and
    deployments that never touch the (Step 3) editor UI are unaffected.

    Per CEO decision #2 (2026-07-28, Section 12 of
    docs/architecture/m8-3-ai-gateway-control-center-plan.md): semantic
    roles stay LOCAL-TIER ONLY. This table is read exclusively by
    `app.ai_gateway.local_model_policy.resolve_local_model()`, which is
    called from exactly one place in this codebase -
    `LocalOllamaProviderClient._resolve_model()`. No cloud `ProviderClient`
    reads this table, directly or indirectly - adding a "coding"/"vision"/
    "reasoning"/"embeddings" row here only ever changes which model the
    LOCAL provider is asked for on a matching capability; it can never
    change which PROVIDER (local/free/premium) `router.py` selects, and it
    can never add role-awareness to Claude/OpenAI/Gemini/Groq - those
    remain governed solely by `default_model`/Provider Management (Step 2).

    `model` is the literal model string to send the local OpenAI-compatible
    server (e.g. "qwen3:8b", "codellama:13b") - the exact same kind of
    value `LOCAL_MODEL_DEFAULT_MODEL`/`LOCAL_MODEL_SECONDARY_MODEL` already
    hold in `.env`; this table is what lets an admin add a THIRD, FOURTH,
    ... role without a new settings key or code deploy (the CEO's own
    "future models addable without business-logic changes" requirement).

    `enabled` (default True) lets an admin temporarily disable a role
    (e.g. the underlying local model was pulled/removed from the Ollama
    host) without deleting the row and losing its capability wiring - a
    disabled role is skipped by `resolve_local_model()` exactly like an
    empty/unset settings attribute already is.

    Deliberately NOT storing "which capability prefers this role" here -
    `CAPABILITY_LOCAL_MODEL_ROLE` (capability -> ordered role-name
    preference) stays a code-level table in `local_model_policy.py`,
    unchanged by this migration. Which underlying MODEL answers to a role
    name is an operational/ops concern (swap the model an admin points
    "research" at as new local models become available); which CAPABILITY
    prefers which role is a business-logic/routing decision, the same
    "business logic never changes, only data grows" line Step 1 already
    drew between `resolve_provider_config()` (DB-backed values) and
    `router.py`'s `CAPABILITY_PROVIDER_PREFERENCE` (code-level routing
    logic, unchanged since M11).

    `updated_by_user_id` mirrors `AIProviderConfig.updated_by_user_id`
    exactly - a convenience "who touched this last" pointer, `ondelete=
    "SET NULL"` so a role's configuration survives the editing user being
    deleted. No dedicated audit table this step (unlike Step 1's
    `AIProviderConfigAudit`) - Section 11 point 3 scopes Step 3 as "DB-backed
    role table + editor UI" only; a role's current `model`/`enabled` value
    plus `updated_at`/`updated_by_user_id` is judged sufficient for a
    non-credential, non-security-sensitive setting. Full change-history
    auditing can be added later the same additive way Step 1's own audit
    table was, if ever needed.
    """

    __tablename__ = "ai_model_roles"

    role_name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    model: Mapped[str] = mapped_column(String(150), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    updated_by_user: Mapped["User | None"] = relationship()
