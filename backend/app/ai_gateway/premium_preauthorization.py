"""
premium_preauthorization.py - M8.3 Step 7 (Premium Approval UI). The
existing-session service layer for `AIPremiumPreauthorization` - used by
`app/api/routes/ai_gateway.py`'s new approve/reject/history endpoints and by
`app/ai_gateway/ui_query.py`'s `list_approvals()` status computation, both
of which already have an open `Session` (via `Depends(get_db)`) and should
never open a second one.

Deliberately separate from `app.ai_gateway.premium_approval_resolver`
(AIGateway's own dependency-inverted read seam, which opens its OWN
short-lived session and is never imported by anything above the Gateway) -
this module is the one `SQLAlchemyPremiumApprovalResolver.is_preauthorized()`
itself delegates the actual query to (`has_live_preauthorization()` below),
so the "what counts as a live grant" filter exists in exactly one place,
not two.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_premium_preauthorization import AIPremiumPreauthorization

DECISION_APPROVED = "approved"
DECISION_REJECTED = "rejected"


def _live_grant_query(db: Session, *, company_profile_id: uuid.UUID, capability: str):
    now = datetime.now(timezone.utc)
    return (
        db.query(AIPremiumPreauthorization)
        .filter(
            and_(
                AIPremiumPreauthorization.company_profile_id == company_profile_id,
                AIPremiumPreauthorization.capability == capability,
                AIPremiumPreauthorization.decision == DECISION_APPROVED,
                AIPremiumPreauthorization.expires_at.isnot(None),
                AIPremiumPreauthorization.expires_at > now,
            )
        )
        .order_by(AIPremiumPreauthorization.expires_at.desc())
    )


def has_live_preauthorization(db: Session, *, company_profile_id: uuid.UUID | None, capability: str) -> bool:
    """The single source of truth for "is this (company, capability) pair
    currently pre-authorized" - reused by both
    `SQLAlchemyPremiumApprovalResolver` (AIGateway's own gate check, a
    fresh short-lived session) and `ui_query.list_approvals()` (an
    already-open request-scoped session, for the `status` field - see that
    function's own docstring)."""
    if company_profile_id is None:
        return False
    return _live_grant_query(db, company_profile_id=company_profile_id, capability=capability).first() is not None


def latest_decision_for(db: Session, *, company_profile_id: uuid.UUID, capability: str) -> AIPremiumPreauthorization | None:
    """Most recent decision (approved OR rejected, live or expired) for
    this (company, capability) pair - used by `ui_query.list_approvals()`
    to compute `ApprovalRequestRead.status`: a live approved row ->
    "approved"; no live approved row but a rejected row exists and is the
    most recent decision -> "rejected"; neither -> "pending". An EXPIRED
    approved row with no later rejection is intentionally still read as
    "pending" by the caller (see ui_query.py) - an expired grant no longer
    protects anything, so a fresh approval-required event for that
    capability/company is, correctly, pending again."""
    return (
        db.query(AIPremiumPreauthorization)
        .filter(
            AIPremiumPreauthorization.company_profile_id == company_profile_id,
            AIPremiumPreauthorization.capability == capability,
        )
        .order_by(AIPremiumPreauthorization.decided_at.desc())
        .first()
    )


def grant_preauthorization(
    db: Session,
    *,
    company_profile_id: uuid.UUID,
    capability: str,
    decision: str,
    decided_by_user_id: uuid.UUID,
    source_request_log_id: uuid.UUID | None = None,
) -> AIPremiumPreauthorization:
    """Writes exactly one new row - never updates an existing one (see
    AIPremiumPreauthorization's own docstring: "never mutated once
    written"). `decision` must be `DECISION_APPROVED`/`DECISION_REJECTED`;
    `expires_at` is set only for an approval
    (`settings.AI_GATEWAY_PREMIUM_PREAUTH_MINUTES` out from `decided_at`),
    left `None` for a rejection - nothing to expire."""
    if decision not in (DECISION_APPROVED, DECISION_REJECTED):
        raise ValueError(f"decision must be {DECISION_APPROVED!r} or {DECISION_REJECTED!r}, got {decision!r}")

    decided_at = datetime.now(timezone.utc)
    expires_at = decided_at + timedelta(minutes=settings.AI_GATEWAY_PREMIUM_PREAUTH_MINUTES) if decision == DECISION_APPROVED else None

    grant = AIPremiumPreauthorization(
        company_profile_id=company_profile_id,
        capability=capability,
        decision=decision,
        decided_by_user_id=decided_by_user_id,
        source_request_log_id=source_request_log_id,
        decided_at=decided_at,
        expires_at=expires_at,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return grant


def list_preauthorization_history(db: Session, *, company_profile_ids: list[uuid.UUID], limit: int = 100) -> list[AIPremiumPreauthorization]:
    """All past decisions (both approved and rejected) for the caller's own
    companies, most recent first - backs `GET /ai-gateway/approvals/history`.
    Scoped by `company_profile_ids` the exact same way every other
    Activity/Approvals/Overview query in `ui_query.py` already scopes to
    `_owned_company_profile_ids()` - see that module's own ISOLATION RULE."""
    if not company_profile_ids:
        return []
    return (
        db.query(AIPremiumPreauthorization)
        .filter(AIPremiumPreauthorization.company_profile_id.in_(company_profile_ids))
        .order_by(AIPremiumPreauthorization.decided_at.desc())
        .limit(limit)
        .all()
    )
