"""M6.3 Reply Intelligence: Thread Builder support - a non-unique index on
email_messages.internet_message_id, and email_messages.to_recipients/
cc_recipients.

The new index (approved M6.3 adjustment #2) is required because Thread
Builder's In-Reply-To/References matching has to search across every
ProviderConnection a company owns, not just one - the existing partial
UNIQUE index from migration 0009
(uq_email_messages_connection_internet_message_id) has provider_connection_id
as its leading column and cannot serve a cross-connection lookup
efficiently. This migration adds a second, plain index with
internet_message_id as the sole/leading column; it does not replace or
alter the migration 0009 index, which continues to enforce dedup exactly
as before.

to_recipients/cc_recipients are a disclosed, additive gap found while
designing Thread Builder itself (not part of the original M6.1/M6.2 field
list, and not explicitly called out in the M6.3 architecture round) -
without them, ConversationParticipant has no way to learn about a CC'd
stakeholder on an inbound message; from_email/from_name only ever
captured the sender. Plain JSONB list columns
(`[{"email": ..., "name": ...}, ...]`), nullable, no new table - see
email_message.py's own docstring for the full reasoning.

Zero changes to any existing column, constraint, or index from prior
migrations. Purely additive, same discipline as every migration since
0002.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("email_messages", sa.Column("to_recipients", postgresql.JSONB(), nullable=True))
    op.add_column("email_messages", sa.Column("cc_recipients", postgresql.JSONB(), nullable=True))

    op.create_index("ix_email_messages_internet_message_id", "email_messages", ["internet_message_id"])


def downgrade() -> None:
    op.drop_index("ix_email_messages_internet_message_id", table_name="email_messages")

    op.drop_column("email_messages", "cc_recipients")
    op.drop_column("email_messages", "to_recipients")
