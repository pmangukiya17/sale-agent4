"""M6.1 Reply Intelligence: the persistent conversation model only -
conversations, email_messages, conversation_participants. Deliberately
narrow, per explicit scoping: no InboxSyncState, no Attachment (both
belong with M6.2's sync engine - neither has any dependent in this
migration's own three tables, so bundling them now would be exactly the
anticipatory-schema mistake this milestone's own design plan flags as a
risk elsewhere), no ReplyAnalysis (M6.4), no Task (M6.5).

Provider-neutral by construction - see
docs/architecture/m6-reply-intelligence-plan.md sections 2-3. provider
identity lives on email_messages.provider as a plain string column,
never as a table/column name or enum value tied to one vendor.

Two new enum types (conversation_status, conversation_participant_role).
Reuses the EXISTING message_direction enum type (created by migration
0001 for the dormant, superseded Message model) via create_type=False -
this migration must not attempt to CREATE TYPE message_direction again.

Zero changes to any existing table. Purely additive, same discipline as
every migration since 0002.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- new enum types ---------------------------------------------------
    conversation_status = postgresql.ENUM(
        "open", "closed", name="conversation_status", create_type=False,
    )
    conversation_participant_role = postgresql.ENUM(
        "to", "cc", "from", name="conversation_participant_role", create_type=False,
    )
    for enum_type in (conversation_status, conversation_participant_role):
        enum_type.create(bind, checkfirst=True)

    # Reused as-is from migration 0001 (the dormant Message model's own
    # direction column) - NOT created here, only referenced.
    message_direction = postgresql.ENUM(
        "outbound", "inbound", name="message_direction", create_type=False,
    )

    # --- conversations: one durable thread, scoped to a business
    # relationship, not a mailbox or a provider (see conversation.py's
    # docstring). ------------------------------------------------------------
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("prospect_contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospect_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider_connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("provider_connections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("conversation_key", sa.String(500), nullable=True),
        sa.Column("status", conversation_status, nullable=False, server_default="open"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_discovered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_conversations_company_profile_id", "conversations", ["company_profile_id"])
    op.create_index("ix_conversations_prospect_id", "conversations", ["prospect_id"])
    op.create_index("ix_conversations_prospect_contact_id", "conversations", ["prospect_contact_id"])
    op.create_index("ix_conversations_provider_connection_id", "conversations", ["provider_connection_id"])
    op.create_index("ix_conversations_status", "conversations", ["status"])
    op.create_index("ix_conversations_last_message_at", "conversations", ["last_message_at"])
    # Composite, not unique - the thread-detection fallback layers (M6.3)
    # are heuristic; forcing uniqueness could wrongly reject a genuinely
    # separate conversation that happens to hash to the same key.
    op.create_index("ix_conversations_company_profile_id_conversation_key", "conversations", ["company_profile_id", "conversation_key"])

    # --- email_messages: one row per individual email, inbound or
    # outbound - the provider-neutral record (see email_message.py's
    # docstring). --------------------------------------------------------
    op.create_table(
        "email_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("provider_connections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("delivery_queue_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("delivery_queue_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("provider_message_id", sa.String(500), nullable=True),
        sa.Column("provider_thread_id", sa.String(500), nullable=True),
        sa.Column("internet_message_id", sa.String(998), nullable=True),
        sa.Column("in_reply_to", sa.String(998), nullable=True),
        sa.Column("references", sa.Text(), nullable=True),
        sa.Column("direction", message_direction, nullable=False),
        sa.Column("from_email", sa.String(255), nullable=True),
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("subject", sa.String(998), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_email_messages_conversation_id", "email_messages", ["conversation_id"])
    op.create_index("ix_email_messages_company_profile_id", "email_messages", ["company_profile_id"])
    op.create_index("ix_email_messages_provider_connection_id", "email_messages", ["provider_connection_id"])
    op.create_index("ix_email_messages_delivery_queue_item_id", "email_messages", ["delivery_queue_item_id"])
    op.create_index("ix_email_messages_provider", "email_messages", ["provider"])
    op.create_index("ix_email_messages_provider_thread_id", "email_messages", ["provider_thread_id"])
    op.create_index("ix_email_messages_in_reply_to", "email_messages", ["in_reply_to"])
    op.create_index("ix_email_messages_direction", "email_messages", ["direction"])
    op.create_index("ix_email_messages_sent_at", "email_messages", ["sent_at"])
    # The real dedup guarantee - RFC 5322 Message-ID is provider-
    # independent, unlike provider_message_id (see this table's docstring).
    # Partial, not a plain unique constraint, because a real (if rare)
    # malformed email can lack this header entirely - see migration 0008's
    # identical partial-unique precedent (uq_delivery_queue_items_active_draft).
    op.create_index(
        "uq_email_messages_connection_internet_message_id",
        "email_messages",
        ["provider_connection_id", "internet_message_id"],
        unique=True,
        postgresql_where=sa.text("internet_message_id IS NOT NULL"),
    )

    # --- conversation_participants: one row per (conversation, email) -
    # see conversation_participant.py's docstring. --------------------------
    op.create_table(
        "conversation_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("role", conversation_participant_role, nullable=False),
        sa.Column("prospect_contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospect_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("conversation_id", "email", name="uq_conversation_participants_conversation_email"),
    )
    op.create_index("ix_conversation_participants_conversation_id", "conversation_participants", ["conversation_id"])
    op.create_index("ix_conversation_participants_email", "conversation_participants", ["email"])
    op.create_index("ix_conversation_participants_prospect_contact_id", "conversation_participants", ["prospect_contact_id"])


def downgrade() -> None:
    op.drop_index("ix_conversation_participants_prospect_contact_id", table_name="conversation_participants")
    op.drop_index("ix_conversation_participants_email", table_name="conversation_participants")
    op.drop_index("ix_conversation_participants_conversation_id", table_name="conversation_participants")
    op.drop_table("conversation_participants")

    op.drop_index("uq_email_messages_connection_internet_message_id", table_name="email_messages")
    op.drop_index("ix_email_messages_sent_at", table_name="email_messages")
    op.drop_index("ix_email_messages_direction", table_name="email_messages")
    op.drop_index("ix_email_messages_in_reply_to", table_name="email_messages")
    op.drop_index("ix_email_messages_provider_thread_id", table_name="email_messages")
    op.drop_index("ix_email_messages_provider", table_name="email_messages")
    op.drop_index("ix_email_messages_delivery_queue_item_id", table_name="email_messages")
    op.drop_index("ix_email_messages_provider_connection_id", table_name="email_messages")
    op.drop_index("ix_email_messages_company_profile_id", table_name="email_messages")
    op.drop_index("ix_email_messages_conversation_id", table_name="email_messages")
    op.drop_table("email_messages")

    op.drop_index("ix_conversations_company_profile_id_conversation_key", table_name="conversations")
    op.drop_index("ix_conversations_last_message_at", table_name="conversations")
    op.drop_index("ix_conversations_status", table_name="conversations")
    op.drop_index("ix_conversations_provider_connection_id", table_name="conversations")
    op.drop_index("ix_conversations_prospect_contact_id", table_name="conversations")
    op.drop_index("ix_conversations_prospect_id", table_name="conversations")
    op.drop_index("ix_conversations_company_profile_id", table_name="conversations")
    op.drop_table("conversations")

    bind = op.get_bind()
    postgresql.ENUM(name="conversation_participant_role", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="conversation_status", create_type=False).drop(bind, checkfirst=True)
