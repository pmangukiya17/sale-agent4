import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import MessageDirection


class EmailMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One individual email, inbound or outbound - the provider-neutral
    record every M6 pipeline stage above the provider-adapter boundary
    operates on (see docs/architecture/m6-reply-intelligence-plan.md
    section 2/3). `provider` is a plain string column here, not an enum or
    a provider-specific table, exactly the convention already used by
    ProviderConnection.provider_key/ProspectSource.provider_key - adding a
    provider is a data-level change, never a schema migration.

    Deliberately NOT included in M6.1 (see the M6.1 design plan's Attachment
    discussion): is_analyzed/attempt_count/max_attempts/last_error, the
    AI-analysis worker's own claim/retry bookkeeping - those describe how
    the AI pipeline processes a message, not what a message is, and arrive
    as a small additive migration when M6.4 actually needs them, matching
    this project's "add columns when the consuming phase needs them"
    discipline.

    Message-ID (internet_message_id) is the real, provider-independent
    dedup key - see its own column note below - deliberately NOT
    provider_message_id, whose availability varies by provider and even
    by code path within one provider (OutlookProvider.send() returns none
    today; see the M6 plan's Provider Capability Matrix).

    company_profile_id is denormalized down from conversation_id, the
    same "let a table filter without joining back up" convention
    DeliveryQueueItem already uses for prospect_id/prospect_contact_id/
    company_profile_id - lets a future business-wide inbox query run
    without joining through conversations.

    One-directional relationships only toward DeliveryQueueItem - see
    Conversation's docstring for the same "point up, never down" boundary
    applied here; DeliveryQueueItem is never edited to add a reciprocal
    back-reference to this table.

    conversation_id is nullable as of M6.2 (migration 0010) - a correction
    over M6.1's original NOT NULL. This is a TEMPORARY PROCESSING STATE,
    not a permanent business state: M6.2's sync worker writes raw,
    provider-normalized messages with conversation_id = NULL because
    conversation-building is explicitly out of that milestone's scope; M6.3
    (Thread Builder) is the ONLY code that ever assigns conversation_id,
    and every message is expected to eventually get one. `WHERE
    conversation_id IS NULL` on this table IS M6.3's work queue - no
    separate threading-status column exists or should be added for this
    (per explicit product decision during M6.2 scoping) unless a real,
    demonstrated need for a richer state machine ever appears. The
    lifecycle is exactly:

        sync worker inserts message (conversation_id = NULL)
              -> M6.3 Thread Builder claims it
              -> conversation_id assigned, row now belongs to a Conversation

    Outbound messages (M6.3+, once send-side correlation exists) are
    expected to always be inserted WITH a conversation_id already known
    (the sending flow already knows which Conversation/Prospect it's
    replying within) - NULL is fundamentally an INBOUND-sync concept, not
    something outbound writers should ever produce.

    to_recipients/cc_recipients (migration 0011, M6.3) - a disclosed gap
    found while implementing Thread Builder, not part of the original
    M6.1/M6.2 field list: ConversationParticipant needs to track CC'd
    stakeholders on INBOUND messages too (a prospect's colleague replying
    on a thread), and there was no column anywhere carrying that
    information - from_email/from_name only ever captured the sender.
    Both are a plain JSONB list of `{"email": ..., "name": ...}` objects,
    same escape-hatch shape used elsewhere in this codebase for
    provider-shaped lists (e.g. ProviderConnection.scopes_granted) -
    deliberately not a separate table (no query anywhere needs to search
    "every message a given CC'd address appears on" independently of
    ConversationParticipant, which already serves that purpose at the
    conversation level). M6.2's OutlookProvider populates these from
    Graph's toRecipients/ccRecipients; dispatch_service (M5) populates
    to_recipients=[{"email": item.recipient_email}] for outbound sends -
    M5 has no CC concept today, so cc_recipients stays empty for every
    outbound row.
    """

    __tablename__ = "email_messages"

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_connections.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Never hard-deleted by disconnect (see ProviderConnection's own
    # docstring), so RESTRICT is not expected to ever actually block a
    # real operation - it documents intent (message history must survive
    # independently of connection lifecycle) rather than guarding against
    # a delete path that exists today.
    delivery_queue_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("delivery_queue_items.id", ondelete="SET NULL"), nullable=True, index=True
    )

    provider: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_thread_id: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    # RFC 5322 Message-ID header - the universal, provider-independent
    # dedup key (see this table's docstring). Nullable at the column
    # level - a real, if rare, malformed email can lack this header - the
    # actual dedup guarantee is the partial unique index in migration
    # 0009 (WHERE internet_message_id IS NOT NULL), not a NOT NULL
    # constraint here, which would make such a message unstorable.
    # Plain (non-unique) index added by migration 0011 - Thread Builder's
    # In-Reply-To/References chain-walk (see thread_matching.py) has to
    # search across every connection a company owns, not just one, so the
    # connection-scoped partial UNIQUE index from migration 0009
    # (uq_email_messages_connection_internet_message_id) - whose leading
    # column is provider_connection_id, not this column - can't serve
    # that lookup efficiently. The two indexes serve different purposes
    # and neither replaces the other.
    internet_message_id: Mapped[str | None] = mapped_column(String(998), nullable=True, index=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(998), nullable=True, index=True)
    references: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_recipients: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    cc_recipients: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    direction: Mapped[MessageDirection] = mapped_column(
        Enum(
            MessageDirection,
            name="message_direction",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )

    from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(998), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    sent_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    received_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # When OUR sync worker actually pulled this row in - distinct from
    # sent_at/received_at (the message's own timestamps) because sync can
    # lag; declared now so M6.2 has a column to write to without another
    # migration, but M6.1 itself never populates it (no sync worker exists
    # yet in this phase's scope).
    synced_at: Mapped[datetime | None] = mapped_column(nullable=True)

    has_attachments: Mapped[bool] = mapped_column(default=False, nullable=False)

    conversation: Mapped["Conversation | None"] = relationship(back_populates="messages")
    company_profile: Mapped["CompanyProfile"] = relationship()
    provider_connection: Mapped["ProviderConnection"] = relationship()
    delivery_queue_item: Mapped["DeliveryQueueItem | None"] = relationship()
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="email_message", cascade="all, delete-orphan"
    )
