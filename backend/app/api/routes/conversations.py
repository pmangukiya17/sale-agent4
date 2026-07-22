import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.conversation import Conversation
from app.models.enums import ConversationStatus
from app.schemas.conversation import ConversationDetailRead, ConversationRead

router = APIRouter()

# M6.5 (Conversations UI): read-only. Every field this router exposes
# already exists, written by M6.1-M6.4 (schema, mailbox sync, thread
# builder, reply intelligence) - no new table, no new write path. The
# CRM-updates milestone (relationship_stage state machine, Task/
# recommended-actions table - docs/architecture/m6-reply-intelligence-
# plan.md's own M6.5) is explicitly deferred; this router never
# references a Task model because none exists yet.


@router.get(
    "/company-profiles/{company_profile_id}/conversations",
    response_model=list[ConversationRead],
)
def list_conversations(
    status_filter: ConversationStatus | None = Query(None, alias="status"),
    needs_human_review: bool | None = Query(None),
    prospect_id: uuid.UUID | None = Query(None),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .where(Conversation.company_profile_id == profile.id)
        .options(selectinload(Conversation.prospect))
        .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.created_at.desc())
    )
    if status_filter is not None:
        stmt = stmt.where(Conversation.status == status_filter)
    if needs_human_review is not None:
        stmt = stmt.where(Conversation.needs_human_review == needs_human_review)
    if prospect_id is not None:
        stmt = stmt.where(Conversation.prospect_id == prospect_id)
    return list(db.scalars(stmt).all())


@router.get(
    "/company-profiles/{company_profile_id}/conversations/{conversation_id}",
    response_model=ConversationDetailRead,
)
def get_conversation(
    conversation_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Conversation:
    conversation = db.scalars(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(
            selectinload(Conversation.prospect),
            selectinload(Conversation.participants),
            selectinload(Conversation.messages),
        )
    ).first()
    if conversation is None or conversation.company_profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation
