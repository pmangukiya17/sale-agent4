"""
AI request logging - M11 (AI Provider Hierarchy). Structured-logs every
attempted AI Gateway call (timestamp - implicit in every log record via
the standard `logging` module, provider, model, tier, capability,
duration, tokens, cost, success/failure, confidence score, and - since
GatewayRequest.company_profile_id/user_id were threaded through from the
caller - workspace/user context) via the standard `logging` module - the
same observability discipline every other point in app.ai_gateway.client
already uses (ai_gateway.provider_call_failed, ai_gateway.soft_budget_exceeded,
etc.), extended into one purpose-built record shape instead of ad-hoc
`extra=` dicts scattered per call site.

`company_profile_id` is this codebase's honest analog to the spec's
"Workspace" field - no separate workspace/multi-user concept exists yet
(see docs/architecture/m11-ai-provider-hierarchy-plan.md Section 3.3);
both fields are optional and only populated for capabilities that have
actually threaded that context down to a GatewayRequest so far (Research,
via LLMAnalysisEngine - see that module's own docstring) - every other
capability logs with these as None until it does the same, no capability
is required to populate them.

M8.2 (AI Gateway Backend Integration) makes good on this module's own
above-stated plan: `ai_request_logs` (migration 0029,
`app.models.ai_request_log.AIRequestLog`) now durably persists every entry
alongside the unchanged structured-log line - `log_ai_request()`'s
signature and every one of its three call sites in `client.py` are
UNTOUCHED; only this function's own body gained a second, additive side
effect. The DB write opens and closes its OWN short-lived session
(`app.db.session.SessionLocal`, the same "worker opens its own session"
convention `app/notifications/worker.py`/`app/delivery/worker.py` already
use) rather than threading a `Session` through `AIGateway`/`GatewayRequest`
- `AIGateway` remains a plain, DB-free class, unchanged. The write is
wrapped in a broad try/except: a logging failure (DB down, migration not
yet applied, etc.) must never raise out of `log_ai_request()` and break
the actual AI Gateway call it's observing - observability is additive,
never load-bearing.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger("app.ai_gateway.request_log")


@dataclass(frozen=True)
class AIRequestLogEntry:
    capability: str
    provider_key: str | None
    model: str | None
    tier: str | None
    duration_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: float | None
    success: bool
    confidence_score: float | None = None
    error_type: str | None = None
    company_profile_id: str | None = None
    user_id: str | None = None


def log_ai_request(entry: AIRequestLogEntry) -> None:
    logger.info(
        "ai_gateway.request_completed" if entry.success else "ai_gateway.request_failed",
        extra={
            "capability": entry.capability,
            "provider_key": entry.provider_key,
            "model": entry.model,
            "tier": entry.tier,
            "duration_ms": entry.duration_ms,
            "prompt_tokens": entry.prompt_tokens,
            "completion_tokens": entry.completion_tokens,
            "cost_usd": entry.cost_usd,
            "confidence_score": entry.confidence_score,
            "error_type": entry.error_type,
            "company_profile_id": entry.company_profile_id,
            "user_id": entry.user_id,
        },
    )
    _persist_ai_request_log(entry)


def _persist_ai_request_log(entry: AIRequestLogEntry) -> None:
    """M8.2 addition. Best-effort DB persistence of `entry` - see module
    docstring for why failures here are swallowed (logged at warning, not
    raised). Imports are all local/lazy (sqlalchemy, the DB session
    factory, and the AIRequestLog model) so this module - and therefore
    `client.py`, which imports it - stays importable in this project's
    pure/sqlalchemy-free test sandbox exactly as it was before this
    addition (see tests/test_ai_provider_hierarchy_pure.py's own
    disclosure of that constraint).

    M8.2 regression-sweep fix: `app.db.base` (which imports every model in
    the codebase, registering them all in SQLAlchemy's mapper registry) is
    imported here BEFORE the AIRequestLog model itself - the same "must be
    imported before any ORM operation that triggers configure_mappers()"
    discipline every worker entrypoint in this codebase already follows
    (app/notifications/worker.py, app/delivery/worker.py, etc. - see
    app/db/base.py's own module docstring and test_conversation_models.py's
    own docstring for the fuller explanation of this exact failure mode).
    log_ai_request() is called from AIGateway.complete()/_walk(), which
    plenty of callers (e.g. test_ai_provider_hierarchy_e2e.py's fake-
    provider-client tests) reach WITHOUT ever otherwise touching the DB
    layer - before this fix, whichever process got there first would be
    the first to trigger configure_mappers() with an incomplete registry
    (AIRequestLog imported, but CompanyProfile - only a lazy string
    forward-reference on its `company_profile` relationship - not yet
    registered), raising "CompanyProfile failed to locate a name" the
    moment `db.add()`/`db.commit()` below configured the mapper for real.
    That exception was already caught by the broad except below (so it
    never broke a real Gateway call), but it should never have been raised
    in the first place - this import is the actual fix, not a suppression
    of the symptom."""
    import uuid
    from datetime import datetime, timezone

    try:
        from app.db import base as _base  # noqa: F401 - registers every model before configure_mappers() runs
        from app.db.session import SessionLocal
        from app.models.ai_request_log import AIRequestLog
    except Exception:  # noqa: BLE001 - sqlalchemy/pydantic_settings genuinely absent in some environments
        logger.debug("ai_gateway.request_log_persist_skipped", extra={"reason": "db_layer_unavailable"})
        return

    def _as_uuid(value: str | None) -> uuid.UUID | None:
        if not value:
            return None
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError, TypeError):
            return None

    db = SessionLocal()
    try:
        db.add(
            AIRequestLog(
                occurred_at=datetime.now(timezone.utc),
                capability=entry.capability,
                provider_key=entry.provider_key,
                model=entry.model,
                tier=entry.tier,
                duration_ms=entry.duration_ms,
                prompt_tokens=entry.prompt_tokens,
                completion_tokens=entry.completion_tokens,
                cost_usd=entry.cost_usd,
                success=entry.success,
                confidence_score=entry.confidence_score,
                error_type=entry.error_type,
                company_profile_id=_as_uuid(entry.company_profile_id),
                user_id=_as_uuid(entry.user_id),
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001 - never let observability break the real Gateway call
        logger.warning("ai_gateway.request_log_persist_failed", exc_info=True)
        db.rollback()
    finally:
        db.close()
