"""
The M6.3 threading algorithm - matches one inbound EmailMessage
(conversation_id IS NULL) to an existing Conversation, or determines none
exists yet. Provider-neutral by construction - nothing here ever reads
`EmailMessage.provider` to change behavior; every signal used
(provider_thread_id, internet_message_id, in_reply_to, references,
subject, participant emails) is already a plain, normalized column by
the time this module ever sees it.

The exact procedure approved in the M6.3 architecture round:

1. Provider thread ID - a fast, PROVISIONAL first-pass match (Graph
   conversationId / Gmail threadId - whatever provider_thread_id already
   carries on this message, matched against other EmailMessage rows on
   the same provider_connection_id already assigned to a Conversation).
2. In-Reply-To - AUTHORITATIVE: the RFC 5322 direct-parent Message-ID.
3. References - AUTHORITATIVE fallback: walks the ancestor chain, nearest
   first, when step 2's exact parent isn't in the system yet.
   Steps 2/3 ALWAYS override step 1 when both resolve and disagree -
   Message-ID identity is a protocol guarantee; provider thread grouping
   is a fast heuristic, trusted only when nothing stronger contradicts
   it. Implemented below by simply checking the authoritative path FIRST
   and only falling back to the provisional one if it found nothing -
   see match_conversation().
4. (Outbound correlation is not a fourth, separate mechanism - it's steps
   2/3 succeeding against a message this business itself sent. See
   dispatch_service.py/conversation_resolver.py for how an outbound row
   gets a reliable internet_message_id in the first place.)
5. Bounded wait: if 1-3 found nothing, but this message's own
   in_reply_to/references suggest a parent that plausibly just hasn't
   synced yet, AND this message is still "young"
   (< UNTHREADED_RETRY_WINDOW_MINUTES), it is left unthreaded for a
   future Thread Builder pass rather than guessed at - see
   thread_builder.py's own handling of MatchDecision.should_wait. This is
   computed from existing timestamps only - no new threading-status
   column, per the M6.2-era product decision this milestone continues to
   honor.
6. Subject fallback - ONLY when nothing above resolves anything AND the
   bounded wait doesn't apply. Strengthened per explicit M6.3 approval:
   requires ALL THREE of (a) normalized subject match via
   Conversation.conversation_key, (b) at least one overlapping
   participant email, (c) the candidate Conversation's status is OPEN.
   Never attaches to a CLOSED conversation via this path - CLOSED
   conversations remain reachable via the authoritative Message-ID paths
   above (a definite reply is a definite reply regardless of status), but
   never via this heuristic one.

If nothing resolves and the bounded wait doesn't apply, thread_builder.py
creates a brand new Conversation - "never silently drop a message" holds
even when every signal is missing.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.conversation_participant import ConversationParticipant
from app.models.email_message import EmailMessage
from app.models.enums import ConversationParticipantRole, ConversationStatus
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.reply_intelligence.conversation_resolver import upsert_participant
from app.reply_intelligence.subject_normalize import normalize_subject

# How long an inbound message with an unresolved In-Reply-To/References
# pointer is allowed to sit unthreaded, waiting for its parent to arrive
# on a later sync pass, before Thread Builder gives up waiting and falls
# through to subject-fallback/new-Conversation creation. Comfortably
# longer than either the mailbox sync worker's or this worker's own poll
# interval, so a parent that's genuinely still mid-backfill has a real
# chance to show up first.
UNTHREADED_RETRY_WINDOW_MINUTES = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MatchDecision:
    conversation: Conversation | None
    should_wait: bool = False


def _match_by_provider_thread_id(db: Session, message: EmailMessage) -> Conversation | None:
    if not message.provider_thread_id:
        return None
    other = db.scalars(
        select(EmailMessage)
        .where(
            EmailMessage.provider_connection_id == message.provider_connection_id,
            EmailMessage.provider_thread_id == message.provider_thread_id,
            EmailMessage.conversation_id.is_not(None),
            EmailMessage.id != message.id,
        )
        .order_by(EmailMessage.sent_at.desc().nullslast())
    ).first()
    if other is None:
        return None
    return db.get(Conversation, other.conversation_id)


def _candidate_parent_message_ids(message: EmailMessage) -> list[str]:
    """Nearest ancestor first: In-Reply-To (the direct parent) ahead of
    References' own chain; within References, the LAST token (nearest to
    this message, per RFC convention of oldest-first ordering) checked
    before earlier ones. De-duplicated, order preserved - In-Reply-To
    commonly repeats as the final References token."""
    ids: list[str] = []
    if message.in_reply_to:
        ids.append(message.in_reply_to.strip())
    if message.references:
        ids.extend(reversed(message.references.split()))
    seen: set[str] = set()
    ordered: list[str] = []
    for msg_id in ids:
        if msg_id and msg_id not in seen:
            seen.add(msg_id)
            ordered.append(msg_id)
    return ordered


def _match_by_message_id_chain(db: Session, message: EmailMessage) -> Conversation | None:
    for msg_id in _candidate_parent_message_ids(message):
        parent = db.scalars(
            select(EmailMessage).where(
                EmailMessage.company_profile_id == message.company_profile_id,
                EmailMessage.internet_message_id == msg_id,
                EmailMessage.conversation_id.is_not(None),
            )
        ).first()
        if parent is not None:
            return db.get(Conversation, parent.conversation_id)
    return None


def _is_still_within_retry_window(message: EmailMessage) -> bool:
    anchor = message.synced_at or message.received_at or message.created_at
    if anchor is None:
        return False
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    return _now() - anchor < timedelta(minutes=UNTHREADED_RETRY_WINDOW_MINUTES)


def _message_participant_emails(message: EmailMessage) -> set[str]:
    emails = {message.from_email} if message.from_email else set()
    for recipient in (message.to_recipients or []) + (message.cc_recipients or []):
        email = recipient.get("email") if isinstance(recipient, dict) else None
        if email:
            emails.add(email)
    return emails


def _match_by_subject_fallback(db: Session, message: EmailMessage) -> Conversation | None:
    key = normalize_subject(message.subject)
    if not key:
        return None
    message_emails = _message_participant_emails(message)
    if not message_emails:
        # Participant overlap is a REQUIRED condition (M6.3 approval
        # adjustment #3) - a message with no known participant at all
        # cannot satisfy it, so there is nothing to check candidates
        # against.
        return None

    candidates = db.scalars(
        select(Conversation).where(
            Conversation.company_profile_id == message.company_profile_id,
            Conversation.conversation_key == key,
            Conversation.status == ConversationStatus.OPEN,  # required condition #3
        )
    ).all()
    for conversation in candidates:
        existing_emails = {
            p.email
            for p in db.scalars(
                select(ConversationParticipant).where(ConversationParticipant.conversation_id == conversation.id)
            ).all()
        }
        if message_emails & existing_emails:  # required condition #2
            return conversation
    return None


def match_conversation(db: Session, message: EmailMessage) -> MatchDecision:
    """The single entry point thread_builder.py calls per candidate
    message. Order of operations implements the conflict rule described
    in this module's own docstring: the authoritative Message-ID chain is
    always checked and always wins if it resolves anything, regardless of
    whether the provisional provider-thread-id match also resolved
    something (possibly to a DIFFERENT Conversation)."""
    authoritative = _match_by_message_id_chain(db, message)
    if authoritative is not None:
        return MatchDecision(conversation=authoritative)

    provisional = _match_by_provider_thread_id(db, message)
    if provisional is not None:
        return MatchDecision(conversation=provisional)

    if _candidate_parent_message_ids(message) and _is_still_within_retry_window(message):
        return MatchDecision(conversation=None, should_wait=True)

    subject_match = _match_by_subject_fallback(db, message)
    if subject_match is not None:
        return MatchDecision(conversation=subject_match)

    return MatchDecision(conversation=None, should_wait=False)


def resolve_prospect_contact_id(db: Session, company_profile_id: uuid.UUID, email: str | None) -> uuid.UUID | None:
    """Identity resolution against ProspectContact.email, scoped to this
    company - ProspectContact has no company_profile_id column of its
    own, so this joins through Prospect the same way every other
    company-scoped ProspectContact query in this codebase already does."""
    if not email:
        return None
    contact = db.scalars(
        select(ProspectContact)
        .join(Prospect, ProspectContact.prospect_id == Prospect.id)
        .where(Prospect.company_profile_id == company_profile_id, ProspectContact.email == email)
    ).first()
    return contact.id if contact else None


def sync_participants_for_message(db: Session, conversation: Conversation, message: EmailMessage) -> None:
    """Upserts every participant this message reveals - FROM (the
    sender), TO, and CC - regardless of whether the Conversation was just
    matched or just created. Never invents a ProspectContact link that
    doesn't already exist (see upsert_participant's own docstring)."""
    if message.from_email:
        upsert_participant(
            db,
            conversation_id=conversation.id,
            email=message.from_email,
            name=message.from_name,
            role=ConversationParticipantRole.FROM_,
            prospect_contact_id=resolve_prospect_contact_id(db, message.company_profile_id, message.from_email),
        )
    for recipient in message.to_recipients or []:
        email = recipient.get("email") if isinstance(recipient, dict) else None
        upsert_participant(
            db,
            conversation_id=conversation.id,
            email=email,
            name=recipient.get("name") if isinstance(recipient, dict) else None,
            role=ConversationParticipantRole.TO,
            prospect_contact_id=resolve_prospect_contact_id(db, message.company_profile_id, email),
        )
    for recipient in message.cc_recipients or []:
        email = recipient.get("email") if isinstance(recipient, dict) else None
        upsert_participant(
            db,
            conversation_id=conversation.id,
            email=email,
            name=recipient.get("name") if isinstance(recipient, dict) else None,
            role=ConversationParticipantRole.CC,
            prospect_contact_id=resolve_prospect_contact_id(db, message.company_profile_id, email),
        )


def create_conversation_for_unmatched_inbound(db: Session, message: EmailMessage) -> Conversation:
    """The "no match found, not worth waiting" terminal case - a brand
    new Conversation seeded entirely from this one inbound message.
    prospect_id/prospect_contact_id resolve via the sender's email if
    recognized, and stay NULL otherwise - an unrecognized sender is a
    legitimate, expected outcome (see Conversation's own docstring), not
    an error."""
    prospect_contact_id = resolve_prospect_contact_id(db, message.company_profile_id, message.from_email)
    prospect_id = None
    if prospect_contact_id is not None:
        contact = db.get(ProspectContact, prospect_contact_id)
        prospect_id = contact.prospect_id if contact is not None else None

    conversation = Conversation(
        company_profile_id=message.company_profile_id,
        provider_connection_id=message.provider_connection_id,
        prospect_id=prospect_id,
        prospect_contact_id=prospect_contact_id,
        subject=message.subject,
        conversation_key=normalize_subject(message.subject) or None,
        status=ConversationStatus.OPEN,
        last_message_at=message.sent_at or message.received_at,
        first_discovered_at=message.received_at or message.sent_at or _now(),
    )
    db.add(conversation)
    db.flush()
    return conversation
