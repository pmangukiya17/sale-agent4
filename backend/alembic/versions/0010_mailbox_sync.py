"""M6.2 Reply Intelligence: mailbox synchronization - MailboxSyncState,
Attachment, and making email_messages.conversation_id nullable.

MailboxSyncState (named per explicit product correction over the M6.2
design proposal's original "InboxSyncState" - the sync checkpoint belongs
to the provider mailbox, not only its Inbox folder) is the sync engine's
own per-connection checkpoint: cursor, last tick's outcome, when it last
ran. One row per ProviderConnection (unique FK).

Attachment is metadata-only (filename/content_type/size_bytes/
provider_attachment_id) - no file content is ever stored. Deferred out of
M6.1 because that phase had no writer for it; M6.2's sync worker is the
first.

email_messages.conversation_id becomes NULLABLE here - a correction over
migration 0009's original NOT NULL. This is framed strictly as a
TEMPORARY PROCESSING STATE, not a new permanent business state: M6.2's
sync worker inserts raw messages with conversation_id = NULL because
conversation-building is out of its scope; M6.3 (Thread Builder) is the
only code that assigns conversation_id, and `WHERE conversation_id IS
NULL` is deliberately kept as M6.3's entire work queue - no additional
threading-status column is introduced (explicit product decision during
M6.2 scoping: "Do not introduce additional threading status columns
unless they become absolutely necessary"). See email_message.py's
docstring for the full lifecycle.

Reuses no existing enum type; introduces one new one, mailbox_sync_status
(ok/error).

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    mailbox_sync_status = postgresql.ENUM(
        "ok", "error", name="mailbox_sync_status", create_type=False,
    )
    mailbox_sync_status.create(bind, checkfirst=True)

    # --- conversation_id becomes a temporary processing marker, not a
    # required field - see this migration's own module docstring and
    # email_message.py's docstring for the full lifecycle. ---------------
    op.alter_column(
        "email_messages",
        "conversation_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # --- mailbox_sync_states: one checkpoint row per ProviderConnection --
    op.create_table(
        "mailbox_sync_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "provider_connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provider_connections.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("sync_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", mailbox_sync_status, nullable=True),
        sa.Column("last_sync_detail", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("provider_connection_id", name="uq_mailbox_sync_states_provider_connection_id"),
    )
    op.create_index("ix_mailbox_sync_states_provider_connection_id", "mailbox_sync_states", ["provider_connection_id"])
    op.create_index("ix_mailbox_sync_states_last_synced_at", "mailbox_sync_states", ["last_synced_at"])
    op.create_index("ix_mailbox_sync_states_last_sync_status", "mailbox_sync_states", ["last_sync_status"])

    # --- attachments: metadata only, one row per attachment on one
    # email_message -------------------------------------------------------
    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "email_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("email_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(500), nullable=True),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("provider_attachment_id", sa.String(500), nullable=True),
    )
    op.create_index("ix_attachments_email_message_id", "attachments", ["email_message_id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_email_message_id", table_name="attachments")
    op.drop_table("attachments")

    op.drop_index("ix_mailbox_sync_states_last_sync_status", table_name="mailbox_sync_states")
    op.drop_index("ix_mailbox_sync_states_last_synced_at", table_name="mailbox_sync_states")
    op.drop_index("ix_mailbox_sync_states_provider_connection_id", table_name="mailbox_sync_states")
    op.drop_table("mailbox_sync_states")

    # NOTE: reversing this requires every existing row to already have a
    # non-NULL conversation_id - if M6.3's Thread Builder hasn't processed
    # every row yet (i.e. any row is still mid-lifecycle, conversation_id
    # IS NULL), this ALTER COLUMN will fail with a NOT NULL violation.
    # That failure is expected and correct in that situation, not a bug in
    # this migration - it means downgrading past M6.2 while unprocessed
    # sync data exists would silently orphan that data's temporary state,
    # which this migration refuses to do silently.
    op.alter_column(
        "email_messages",
        "conversation_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    bind = op.get_bind()
    postgresql.ENUM(name="mailbox_sync_status", create_type=False).drop(bind, checkfirst=True)
