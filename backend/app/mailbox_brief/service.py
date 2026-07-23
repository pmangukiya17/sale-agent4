"""
Mailbox Brief service - Track C5 (dashboard-capabilities-architecture-
plan.md, Section 6). The only module that writes MailboxBrief rows -
mirrors app.opportunities.service's "service is the only writer" boundary.
app/api/routes/mailbox_brief.py's POST .../generate route is the only
caller of generate_brief; GET .../mailbox-brief calls get_latest_brief,
which never writes anything - reading the latest brief must never have
the side effect of creating a new one, per the CEO's explicit "do not
regenerate automatically" requirement.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mailbox_brief.context import assemble_context
from app.mailbox_brief.engine.base import MailboxBriefEngine
from app.mailbox_brief.engine.deterministic_stub import DeterministicMailboxBriefEngine
from app.models.company_profile import CompanyProfile
from app.models.mailbox_brief import MailboxBrief

_DEFAULT_ENGINE: MailboxBriefEngine = DeterministicMailboxBriefEngine()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_brief(
    db: Session,
    company_profile: CompanyProfile,
    *,
    requested_by_user_id: uuid.UUID | None = None,
    engine: MailboxBriefEngine | None = None,
) -> MailboxBrief:
    """The explicit "Generate New Brief" action - assembles a fresh,
    bounded context from Conversation/Recommendation/Opportunity data
    (never new business data of its own - see MailboxBriefContext's own
    docstring), synthesizes an outcome via the pluggable engine (the
    deterministic stub today, a real LLM-backed engine later with zero
    signature change), and persists exactly one new MailboxBrief row.
    Never mutates or replaces a prior brief - each generation is its own
    durable snapshot, same "every explicit action produces a new row"
    discipline OpportunityStageHistory already established.
    """
    active_engine = engine or _DEFAULT_ENGINE
    context = assemble_context(db, company_profile)
    outcome = active_engine.synthesize(context)

    brief = MailboxBrief(
        company_profile_id=company_profile.id,
        generated_at=_now(),
        ai_provider=outcome.ai_provider,
        ai_model=outcome.ai_model,
        summary=outcome.summary,
        recommendations=[
            {
                "title": rec.title,
                "rationale": rec.rationale,
                "source_type": rec.source_type,
                "source_id": str(rec.source_id) if rec.source_id is not None else None,
            }
            for rec in outcome.recommendations
        ],
        statistics=outcome.statistics,
        requested_by_user_id=requested_by_user_id,
    )
    db.add(brief)
    db.commit()
    db.refresh(brief)
    return brief


def get_latest_brief(db: Session, company_profile_id: uuid.UUID) -> MailboxBrief | None:
    """Read-only - never generates. Returns None if no brief has ever
    been generated for this business yet (an honest "nothing here yet"
    state, not an error)."""
    stmt = (
        select(MailboxBrief)
        .where(MailboxBrief.company_profile_id == company_profile_id)
        .order_by(MailboxBrief.generated_at.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()
