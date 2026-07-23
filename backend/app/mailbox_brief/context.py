"""
MailboxBriefContext - assembles the bounded, read-only projection over
existing CRM data a MailboxBriefEngine synthesizes from. Every query here
is scoped to one company_profile_id (the same isolation boundary every
other Track C read endpoint uses) and capped (top 5 conversations needing
review, top 5 cross-portfolio recommendations) - per the architecture
doc's own "assembles a bounded context (most recent N conversations,
capped, not the whole mailbox history)" requirement, carried over from
Section 6.2 even though this initial slice uses a deterministic engine
rather than a real LLM call.

Deliberately reuses app.opportunities.service's own compute_funnel/
compute_pipeline_value rather than re-deriving that aggregation a second
time - per the CEO's explicit "do not create duplicate business data"
instruction, applied here to computation, not just storage.
"""
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.company_profile import CompanyProfile
from app.models.conversation import Conversation
from app.models.enums import ConversationStatus, RecommendationStatus
from app.models.prospect import Prospect
from app.models.recommendation import Recommendation
from app.opportunities.service import compute_funnel, compute_pipeline_value

NEEDS_REVIEW_LIMIT = 5
TOP_RECOMMENDATIONS_LIMIT = 5


@dataclass(frozen=True)
class ConversationNeedingReview:
    id: uuid.UUID
    subject: str | None
    reply_status: str | None


@dataclass(frozen=True)
class TopRecommendation:
    id: uuid.UUID
    title: str
    recommendation_type: str
    confidence: float | None
    prospect_name: str


@dataclass(frozen=True)
class MailboxBriefContext:
    company_profile: CompanyProfile
    open_conversations_count: int
    needs_review_conversations: list[ConversationNeedingReview] = field(default_factory=list)
    top_recommendations: list[TopRecommendation] = field(default_factory=list)
    funnel: list[dict] = field(default_factory=list)
    pipeline_value: list[dict] = field(default_factory=list)


def assemble_context(db: Session, company_profile: CompanyProfile) -> MailboxBriefContext:
    open_conversations_count = db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.company_profile_id == company_profile.id, Conversation.status == ConversationStatus.OPEN)
    ) or 0

    needs_review_stmt = (
        select(Conversation)
        .where(Conversation.company_profile_id == company_profile.id, Conversation.needs_human_review.is_(True))
        .order_by(Conversation.last_reply_at.desc().nullslast())
        .limit(NEEDS_REVIEW_LIMIT)
    )
    needs_review_conversations = [
        ConversationNeedingReview(
            id=conversation.id,
            subject=conversation.subject,
            reply_status=conversation.reply_status.value if conversation.reply_status else None,
        )
        for conversation in db.scalars(needs_review_stmt).all()
    ]

    recommendations_stmt = (
        select(Recommendation, Prospect.name)
        .join(Prospect, Recommendation.prospect_id == Prospect.id)
        .where(Prospect.company_profile_id == company_profile.id, Recommendation.status == RecommendationStatus.NEW)
        .order_by(Recommendation.confidence.desc().nullslast(), Recommendation.created_at.desc())
        .limit(TOP_RECOMMENDATIONS_LIMIT)
    )
    top_recommendations = [
        TopRecommendation(
            id=recommendation.id,
            title=recommendation.title,
            recommendation_type=recommendation.recommendation_type.value,
            confidence=recommendation.confidence,
            prospect_name=prospect_name,
        )
        for recommendation, prospect_name in db.execute(recommendations_stmt).all()
    ]

    funnel = compute_funnel(db, company_profile.id)
    pipeline_value = compute_pipeline_value(db, company_profile.id)

    return MailboxBriefContext(
        company_profile=company_profile,
        open_conversations_count=open_conversations_count,
        needs_review_conversations=needs_review_conversations,
        top_recommendations=top_recommendations,
        funnel=funnel,
        pipeline_value=pipeline_value,
    )
