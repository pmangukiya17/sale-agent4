import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, UUIDPrimaryKeyMixin


class AIProviderConfigAudit(UUIDPrimaryKeyMixin, Base):
    """
    M8.3 (AI Gateway Management & Control, Step 1). Lightweight, append-only
    audit trail for `AIProviderConfig` changes - the CEO's explicit
    refinement: "Record who changed provider configuration. Record when it
    changed. Record what fields changed. Rollback is not required in
    M8.3." This table is exactly that and nothing more - one row per SAVE
    (never per field), no previous-full-snapshot/rollback support, no
    `TimestampMixin` (an explicit `changed_at` column is used instead,
    mirroring `AIRequestLog.occurred_at`'s own precedent for "this
    timestamp IS the domain fact, not incidental row metadata").

    `field_changes` (JSONB) is `{field_name: {"old": ..., "new": ...}}` for
    every field that actually changed in one save - never a diff for an
    unchanged field, and a save that changes nothing writes NO audit row at
    all (see `provider_config.save_provider_config()`'s own docstring).

    `api_key` is NEVER recorded here as plaintext, in either direction -
    only a presence marker (`"unset"`/`"set"`) is stored for that one
    field, e.g. `{"api_key": {"old": "unset", "new": "set"}}` - this table
    is an operational audit log, not a secondary place a credential could
    leak from. Every OTHER field (`enabled`, `base_url`, `default_model`,
    `extra_settings`) is non-secret and recorded with its real old/new
    value, since knowing exactly what changed is the entire point of this
    table.

    `changed_by_user_id` is nullable / `ondelete="SET NULL"` - the audit
    record of a change must outlive the user who made it being deleted,
    same reasoning as `AIProviderConfig.updated_by_user_id`.
    """

    __tablename__ = "ai_provider_config_audits"

    provider_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    changed_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    field_changes: Mapped[dict] = mapped_column(JSONB, nullable=False)

    changed_by_user: Mapped["User | None"] = relationship()
