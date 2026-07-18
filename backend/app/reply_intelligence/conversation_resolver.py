"""
Conversation/ConversationParticipant read-or-create logic, shared by both
writers of these tables: dispatch_service.py (M5, synchronous, outbound -
it already knows exactly who a send is going to) and thread_builder.py
(M6.3, asynchronous, inbound - it has to figure out who a message
belongs to via thread_matching.py's 6-step algorithm). Both need "find
the right Conversation for this business relationship, or start one" and
"record/refresh this participant" - this module is the one place either
piece of logic lives, so the two call sites can never quietly drift apart
on what either operation means.
"""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.conversation_participant import ConversationParticipant
from app.models.enums import ConversationParticipantRole, ConversationStatus
from app.reply_intelligence.subject_normalize import normalize_subject


def get_or_create_conversation_for_outbound(
    db: Session,
    *,
    company_profile_id: uuid.UUID,
    provider_connection_id: uuid.UUID,
    prospect_id: uuid.UUID | None,
    prospect_contact_id: uuid.UUID | None,
    subject: str | None,
    sent_at: datetime,
) -> Conversation:
    """Called synchronously by dispatch_service at send time - it already
    knows exactly who this email is going to, so this is a plain lookup/
    create, never a heuristic match (heuristic matching is exclusively
    thread_matching.py's job, and only ever applies to inbound messages).

    Reuses an OPEN Conversation already scoped to this exact
    (company_profile_id, provider_connection_id, prospect_contact_id)
    triple if one exists; otherwise starts a new one.

    A CLOSED Conversation for the same triple is deliberately NOT reused
    here - an outbound send to a contact whose prior thread was marked
    CLOSED starts a fresh Conversation rather than silently reopening an
    old one. (Nothing in M6.1-M6.3 actually transitions a row to CLOSED
    yet - see ConversationStatus's own docstring - but this function's
    behavior is written for when something eventually does.)
    """
    query = select(Conversation).where(
        Conversation.company_profile_id == company_profile_id,
        Conversation.provider_connection_id == provider_connection_id,
        Conversation.status == ConversationStatus.OPEN,
    )
    if prospect_contact_id is not None:
        query = query.where(Conversation.prospect_contact_id == prospect_contact_id)
    else:
        # No resolved contact - a rare case for an M5 send (which today
        # always targets a specific ProspectContact), kept here so this
        # function stays correct for any future caller that isn't always
        # contact-resolved, rather than assuming one shape of caller.
        query = query.where(Conversation.prospect_id == prospect_id, Conversation.prospect_contact_id.is_(None))

    existing = db.scalars(query.order_by(Conversation.last_message_at.desc().nullslast())).first()
    if existing is not None:
        if existing.last_message_at is None or sent_at > existing.last_message_at:
            existing.last_message_at = sent_at
        return existing

    conversation = Conversation(
        company_profile_id=company_profile_id,
        provider_connection_id=provider_connection_id,
        prospect_id=prospect_id,
        prospect_contact_id=prospect_contact_id,
        subject=subject,
        conversation_key=normalize_subject(subject) or None,
        status=ConversationStatus.OPEN,
        last_message_at=sent_at,
        first_discovered_at=sent_at,
    )
    db.add(conversation)
    db.flush()
    return conversation


def upsert_participant(
    db: Session,
    *,
    conversation_id: uuid.UUID,
    email: str | None,
    name: str | None,
    role: ConversationParticipantRole,
    prospect_contact_id: uuid.UUID | None = None,
) -> ConversationParticipant | None:
    """Create-if-missing by (conversation_id, email) - the exact unique
    constraint migration 0009 already declared
    (uq_conversation_participants_conversation_email). A returning
    participant's role is updated to whichever role they most recently
    appeared as (matching ConversationParticipant's own documented
    semantics) rather than appended as a duplicate row or left stale.
    No-op (returns None) if email is falsy - a malformed/missing address
    is not worth a participant row, matching the same "never invent what
    wasn't observed" discipline used throughout M6."""
    if not email:
        return None
    existing = db.scalars(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.email == email,
        )
    ).first()
    if existing is not None:
        existing.role = role
        if name and not existing.name:
            existing.name = name
        if prospect_contact_id and not existing.prospect_contact_id:
            existing.prospect_contact_id = prospect_contact_id
        return existing

    participant = ConversationParticipant(
        conversation_id=conversation_id,
        email=email,
        name=name,
        role=role,
        prospect_contact_id=prospect_contact_id,
    )
    db.add(participant)
    db.flush()
    return participant
