"""
Pure normalization helpers - no I/O, no DB session, no network - so they
are unit-testable without Docker/Postgres, same "retroactively extract
pure helpers with tests" precedent M5 Layer 3 established (see
app/delivery/scheduler/windows.py, app/delivery/credentials/payload_codec.py).

Converts a provider-neutral RawEmailMessage/RawAttachment (see
app/delivery/providers/base.py) into the exact kwargs dicts
sync_worker.py passes to EmailMessage(**kwargs)/Attachment(**kwargs) - the
one place that knows how a provider's normalized output maps onto this
project's ORM columns, kept separate from sync_worker.py's own DB/session
orchestration so that mapping can be tested directly.
"""
import uuid
from datetime import datetime

from app.delivery.providers.base import RawAttachment, RawEmailMessage, RawRecipient
from app.models.enums import MessageDirection


def _recipients_to_jsonb(recipients: list[RawRecipient]) -> list[dict]:
    """RawRecipient -> the plain {"email":..., "name":...} dict shape
    EmailMessage.to_recipients/cc_recipients (JSONB) actually stores -
    dataclasses aren't JSON-serializable as-is, so this conversion has to
    happen somewhere; normalize.py is the one place that already owns
    "adapter-neutral struct -> ORM-column-shape" mapping."""
    return [{"email": r.email, "name": r.name} for r in recipients]


def raw_message_to_email_message_kwargs(
    raw: RawEmailMessage,
    *,
    company_profile_id: uuid.UUID,
    provider_connection_id: uuid.UUID,
    provider_key: str,
    synced_at: datetime,
) -> dict:
    """conversation_id is always None here, by construction - M6.2 never
    assigns one (see email_message.py's docstring for the full
    lifecycle); direction is always INBOUND - M6.2's
    IncrementalSyncCapable is an inbound-only interface (see that class's
    own docstring), so nothing upstream of this function ever has an
    outbound RawEmailMessage to normalize."""
    return dict(
        conversation_id=None,
        company_profile_id=company_profile_id,
        provider_connection_id=provider_connection_id,
        provider=provider_key,
        provider_message_id=raw.provider_message_id,
        provider_thread_id=raw.provider_thread_id,
        internet_message_id=raw.internet_message_id,
        in_reply_to=raw.in_reply_to,
        references=raw.references,
        direction=MessageDirection.INBOUND,
        from_email=raw.from_email,
        from_name=raw.from_name,
        subject=raw.subject,
        body_text=raw.body_text,
        body_html=raw.body_html,
        sent_at=raw.sent_at,
        received_at=raw.received_at,
        synced_at=synced_at,
        has_attachments=raw.has_attachments,
        to_recipients=_recipients_to_jsonb(raw.to_recipients),
        cc_recipients=_recipients_to_jsonb(raw.cc_recipients),
    )


def raw_attachment_to_kwargs(raw: RawAttachment) -> dict:
    """email_message_id is deliberately NOT included - the caller
    (sync_worker._persist_message) sets it once the parent EmailMessage
    row has a real id (post-flush), which this pure function has no way
    to know in advance."""
    return dict(
        filename=raw.filename,
        content_type=raw.content_type,
        size_bytes=raw.size_bytes,
        provider_attachment_id=raw.provider_attachment_id,
    )
