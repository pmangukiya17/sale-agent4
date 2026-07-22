import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ConversationParticipantRole, ConversationStatus, MessageDirection, ReplyStatus


class ConversationProspectSummary(BaseModel):
    """M6.5 (Conversations UI): the minimal Prospect projection a
    conversation list/detail view needs - never the full ProspectRead
    shape, to keep this schema honestly scoped to what the UI actually
    renders (a name to link through to the Prospect page), not a
    speculative reuse of an unrelated schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class ConversationParticipantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None
    role: ConversationParticipantRole
    prospect_contact_id: uuid.UUID | None


class EmailMessageRead(BaseModel):
    """Both inbound and outbound legs of a conversation are already the
    same row shape (direction distinguishes them) - see email_message.py's
    own docstring on why this table IS the unified timeline, with no
    separate interleaving of DeliveryQueueItem/OutreachDraft history
    required. body_html is included, not just body_text, since
    OutlookProvider (the only implemented provider today) never populates
    body_text - see app/core/text_extraction.py's own docstring for this
    exact, already-disclosed gap; the frontend is responsible for safely
    rendering body_html (DOMPurify, same as ProspectOutreach.tsx already
    does for signature_html)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    direction: MessageDirection
    from_email: str | None
    from_name: str | None
    subject: str | None
    body_text: str | None
    body_html: str | None
    sent_at: datetime | None
    received_at: datetime | None
    has_attachments: bool


class ConversationRead(BaseModel):
    """List-view projection - no messages/participants (see
    ConversationDetailRead for those), keeping the list endpoint cheap for
    a business-wide table (mirrors DeliveryCampaigns's own list/detail
    split)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    prospect_id: uuid.UUID | None
    prospect: ConversationProspectSummary | None
    subject: str | None
    status: ConversationStatus
    last_message_at: datetime | None
    reply_status: ReplyStatus | None
    last_reply_at: datetime | None
    last_reply_from: str | None
    needs_human_review: bool
    created_at: datetime


class ConversationDetailRead(ConversationRead):
    participants: list[ConversationParticipantRead]
    messages: list[EmailMessageRead]
