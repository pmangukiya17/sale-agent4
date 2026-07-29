"""
PremiumApprovalResolver - M8.3 Step 7 (Premium Approval UI). The one seam
between AIGateway's decision path and persistence, added specifically per
CEO review (2026-07-29): "I do not want AIGateway becoming directly coupled
to database access." AIGateway depends on this abstraction (a plain ABC
with one method) and NEVER on SQLAlchemy, the `AIPremiumPreauthorization`
model, or a DB session directly - see client.py's own `_resolve_premium_approval_resolver()`
for the injection point, which mirrors the exact same testability-seam
shape `provider_lookup` already established (M7.2 precedent).

Desired dependency direction, exactly as specified:

    AIGateway
        v
    PremiumApprovalResolver   (this module - the abstract seam)
        v
    Database implementation   (SQLAlchemyPremiumApprovalResolver below -
                                swappable later for a cache, a policy
                                engine, a distributed approval service,
                                etc. without AIGateway itself changing)

Deliberately lightweight - one ABC, one method, one concrete implementation
- not a large refactor. `AIGateway` imports this module lazily, inside a
method body (see client.py), the same discipline `_resolve_provider()`
already uses for `app.ai_gateway.providers.registry` - this keeps
`app.ai_gateway.client` itself free of any top-level import that would
require sqlalchemy, so it stays importable in this project's pure/
sqlalchemy-free test sandbox exactly as it was before this addition.

This module's own top-level imports are deliberately sqlalchemy-free for
the same reason - only `abc`/`uuid`/`logging`, all stdlib. The concrete
`SQLAlchemyPremiumApprovalResolver` below imports sqlalchemy/the DB layer
lazily, inside its own method, matching `app/ai_gateway/request_log.py`'s
own `_persist_ai_request_log()` precedent for the identical reason.
"""
import logging
import uuid
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class PremiumApprovalResolver(ABC):
    """Abstract seam AIGateway depends on. One method, deliberately - this
    is a yes/no gate check, not a general-purpose query API."""

    @abstractmethod
    def is_preauthorized(self, *, company_profile_id: str | None, capability: str) -> bool:
        """True if a live (decision="approved", not yet expired)
        pre-authorization exists for this exact (company_profile_id,
        capability) pair - see app.models.ai_premium_preauthorization's own
        docstring for the full scope/expiry semantics.

        `company_profile_id` is `str | None`, matching
        `GatewayRequest.company_profile_id`'s own type exactly (that field
        is logging-only/string-typed throughout app.ai_gateway - see
        request.py's own docstring) - an implementation backed by a UUID
        primary key converts internally, the same `_as_uuid()`-shaped
        defensive parse `app.ai_gateway.request_log._persist_ai_request_log()`
        already uses for the identical field.

        Contract every implementation MUST honor:
          - `company_profile_id=None`, or a value that isn't a valid UUID
            -> always False (no scope to check against - the same safe
            default app.ai_gateway.ui_query.py's own user/company-scoping
            already applies everywhere else in this codebase for "owner
            can't be determined").
          - Any underlying error (DB down, migration not yet applied, etc.)
            -> must resolve to False, NEVER raise, NEVER silently True.
            This is a cost-control gate, not a caching optimization - a
            failure here must always fall back to REQUIRING approval, the
            same "observability failures must never break/bypass the real
            call" discipline app.ai_gateway.request_log.log_ai_request()
            already established, applied here to the opposite (safety-
            critical) direction: fail toward MORE scrutiny, never less."""
        raise NotImplementedError


class SQLAlchemyPremiumApprovalResolver(PremiumApprovalResolver):
    """The only concrete implementation today. Opens its own short-lived
    `SessionLocal()` per check - never a caller-provided session, since
    `AIGateway` itself has none to give it (it remains, deliberately, a
    plain DB-free class in every other respect - see client.py's own
    module docstring). Delegates the actual query to
    `app.ai_gateway.premium_preauthorization.has_live_preauthorization()`
    (an existing-session function, reused rather than duplicated, since
    that same query is also needed by `ui_query.py`'s status computation
    with an already-open session) rather than querying inline here."""

    def is_preauthorized(self, *, company_profile_id: str | None, capability: str) -> bool:
        if not company_profile_id:
            return False

        try:
            company_profile_uuid = uuid.UUID(str(company_profile_id))
        except (ValueError, AttributeError, TypeError):
            return False

        try:
            from app.db import base as _base  # noqa: F401 - see request_log.py's own docstring for why this must come first
            from app.db.session import SessionLocal
            from app.ai_gateway.premium_preauthorization import has_live_preauthorization
        except Exception:  # noqa: BLE001 - sqlalchemy/pydantic_settings genuinely absent in some environments
            logger.debug("ai_gateway.premium_preauthorization_check_skipped", extra={"reason": "db_layer_unavailable"})
            return False

        db = SessionLocal()
        try:
            return has_live_preauthorization(db, company_profile_id=company_profile_uuid, capability=capability)
        except Exception:  # noqa: BLE001 - fail SAFE (require approval), never fail open
            logger.warning("ai_gateway.premium_preauthorization_check_failed", exc_info=True)
            return False
        finally:
            db.close()


_default_resolver: PremiumApprovalResolver | None = None


def get_premium_approval_resolver() -> PremiumApprovalResolver:
    """Process-wide default, lazily constructed - same "module-level
    singleton, built on first use" shape as app.realtime.broadcaster.BROADCASTER,
    just lazy here since constructing it needs no external state (nothing
    to defer)."""
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = SQLAlchemyPremiumApprovalResolver()
    return _default_resolver
