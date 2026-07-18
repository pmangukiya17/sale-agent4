import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import MailboxSyncStatus


class MailboxSyncState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One row per ProviderConnection - the sync engine's own checkpoint, not
    a mailbox-content table. Named MailboxSyncState (not InboxSyncState,
    the M6.2 design proposal's original name) per explicit product
    correction: the sync state belongs to the provider mailbox as a whole,
    not only its Inbox folder - a single row today tracks Inbox-only sync
    (see sync_worker.py's docstring), but the name itself doesn't bake
    that scope in, so tracking Sent/Drafts/Archive per-connection later
    doesn't require a rename. If per-folder cursors are ever needed, that
    is a `folder` column addition (or a second table) on this same
    concept, not a redesign.

    One-to-one with ProviderConnection (unique FK, enforced below) -
    deliberately not a growing history table: only the CURRENT checkpoint
    matters for resuming sync; DeliveryEvent-style append-only history is
    not needed here because "what happened last tick" is fully captured by
    last_sync_status/last_sync_detail/last_synced_at on this one row, and
    EmailMessage rows themselves ARE the durable history of what sync
    actually produced.

    cursor is an opaque, provider-defined string (Outlook: a Graph delta
    token extracted from @odata.deltaLink; a future Gmail implementation
    would store its own historyId here) - never parsed or interpreted
    outside the owning provider's fetch_messages_incremental()
    implementation, same "opaque to everyone but its owner" discipline as
    ProviderCredential's encrypted payload.

    sync_window_start is set once, on the FIRST successful tick for this
    connection (cursor was None going in) - the lower bound the initial
    sync was scoped to (see OutlookProvider.fetch_messages_incremental's
    docstring for why an unbounded initial delta sync is avoided). Kept
    purely as an observability/debugging field ("why don't I see anything
    older than this") - nothing reads it to make a decision; the cursor
    alone is what actually drives subsequent ticks.

    ondelete=RESTRICT on provider_connection_id, matching Conversation's/
    EmailMessage's own RESTRICT toward the same table - a ProviderConnection
    is never hard-deleted (see its own docstring), so this is intent, not a
    delete path that exists today.
    """

    __tablename__ = "mailbox_sync_states"

    provider_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("provider_connections.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_window_start: Mapped[datetime | None] = mapped_column(nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)

    last_sync_status: Mapped[MailboxSyncStatus | None] = mapped_column(
        Enum(
            MailboxSyncStatus,
            name="mailbox_sync_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
        index=True,
    )
    # Free-text detail for the last tick - a provider error message, or
    # None on a clean OK tick. Same escape-hatch convention as
    # ProviderConnection.last_verification_detail.
    last_sync_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Consecutive failed-tick count, reset to 0 on the next OK tick - not
    # yet consumed by any backoff logic in M6.2 (every connection is
    # polled every tick regardless of this value); declared now so a
    # future backoff policy is an additive read of an existing column, not
    # another migration.
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    provider_connection: Mapped["ProviderConnection"] = relationship()
