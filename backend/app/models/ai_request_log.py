import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AIRequestLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    M8.2 (AI Gateway Backend Integration). Durable persistence for every
    attempted AI Gateway call - the exact migration
    `app.ai_gateway.request_log`'s own docstring already anticipated:
    "Deliberately NOT a new database table this phase... A future
    migration can add an ai_request_logs table and swap
    log_ai_request()'s body to also INSERT a row - callers of this
    function never need to change." This is that migration.

    One row per `app.ai_gateway.request_log.AIRequestLogEntry` passed to
    `log_ai_request()` - every column here mirrors that dataclass field
    for field. This table is a purely ADDITIVE persistence layer
    underneath an unchanged logging call site (`client.py`'s three
    `log_ai_request(...)` calls are not touched by this milestone) - never
    a second, independently-shaped source of truth for the same event.

    `company_profile_id`/`user_id` are BOTH NULLABLE - most capabilities in
    this codebase don't thread that context into a `GatewayRequest` yet
    (see `AIRequestLogEntry`'s own docstring: "every other capability logs
    with these as None until it does the same"). A row with
    `company_profile_id=None` is a normal, expected state, not an error -
    AI Gateway UI endpoints that need per-user isolation (Activity,
    Usage, Approvals - see `app/ai_gateway/ui_query.py`) simply exclude
    such rows from a user-scoped view rather than guessing an owner.

    `ondelete="SET NULL"` (not CASCADE, not RESTRICT) on
    `company_profile_id` - deliberately outside Track A's CASCADE-vs-
    RESTRICT lifecycle debate for "real" business data: a request log is a
    historical, immutable observability record, not a business entity
    with its own delete lifecycle. Deleting a CompanyProfile should never
    be blocked by (RESTRICT) or silently destroy (CASCADE) its old AI
    request logs - the log row survives as an anonymized historical
    record instead, exactly like `Notification.company_profile_id` already
    does (see that model's own precedent).
    """

    __tablename__ = "ai_request_logs"

    occurred_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider_key: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    company_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    company_profile: Mapped["CompanyProfile | None"] = relationship()
