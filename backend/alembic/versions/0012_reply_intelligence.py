"""M6.4 Reply Intelligence: Conversation reply-classification fields.

Adds a new Postgres enum type (reply_status: positive/negative/neutral/
out_of_office) and four new columns on conversations - reply_status,
last_reply_at, last_reply_from, needs_human_review. All four are
written exclusively by app/reply_intelligence/reply_intelligence_worker.py
(see that module's and Conversation's own docstrings for the full
reasoning) and describe the Conversation's current state only - no new
table, no per-message analysis history, per the explicit M6.4 scope
decision (Conversation-only, no ReplyAnalysis table).

needs_human_review is NOT NULL DEFAULT false - unlike the other three
(nullable, meaning "no reply yet"), "does this need a human" is never
itself ambiguous: false is the correct, real value for a Conversation
with no reply yet, not a placeholder for "unknown."

Zero changes to any existing column, constraint, or index from prior
migrations. Purely additive, same discipline as every migration since
0002.

Migration hygiene fix (post-M6.4-verification): the original version of
this migration created the enum via
`sa.Enum(...).create(op.get_bind(), checkfirst=True)` - the same
`postgresql.ENUM(...).create(bind, checkfirst=True)` idiom migration
0009 already uses for conversation_status/conversation_participant_role.
checkfirst does an application-side "does pg_type already have this
name" SELECT before issuing CREATE TYPE - not atomic against Postgres
itself, and Postgres has no `CREATE TYPE IF NOT EXISTS` (unlike
`CREATE TABLE`/`DROP TYPE`, both of which DO support `IF [NOT] EXISTS`).
This project's docker-compose.yml deliberately runs `alembic upgrade
head` from five containers concurrently on every boot (backend + four
workers - see that file's own "Running migrations from two containers on
startup is safe" comment): normally harmless, because by the time
multiple containers race, the migration in question has usually already
been fully applied and committed by an earlier run, so every later
container's own upgrade attempt finds itself already at head and no-ops
before ever reaching this file's upgrade() body. Migration 0012 was the
first migration in this project to introduce a brand-new enum type on
its FIRST-EVER application - all five containers can reach this
upgrade() body in the same few milliseconds, all observe "reply_status
does not exist yet" via checkfirst's SELECT before any of them commits
its own CREATE TYPE, and every container after the winner fails with
Postgres's own "duplicate key value violates unique constraint
pg_type_typname_nsp_index". Not a functional failure (the losing
container's restart-on-crash simply re-runs alembic, which by then finds
0012 already applied and no-ops correctly) and not a schema problem -
purely a concurrency-safety gap in HOW the type was created.

Fixed by creating the type through a `DO $$ ... EXCEPTION WHEN
duplicate_object THEN NULL; END $$` block - the standard Postgres idiom
for a truly idempotent CREATE TYPE, safe under concurrent execution
because the existence check and the CREATE happen as one atomic
statement inside Postgres itself, not as two separate round-trips from
application code. `create_type=False` is set on every `postgresql.ENUM`
reference below so SQLAlchemy's own DDL emission never attempts a second,
redundant CREATE TYPE when the type is referenced by add_column - the
type is created exactly once, explicitly, by the block below. No schema
redesign: the resulting type and columns are byte-for-byte identical to
the original version of this migration. downgrade()'s DROP TYPE keeps
using `IF EXISTS`, which Postgres supports directly (no DO block needed
there - only CREATE TYPE lacks the IF NOT EXISTS clause).

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False on every reference below - the type is created
# exactly once, explicitly, via the idempotent DO block in upgrade();
# SQLAlchemy must never attempt its own auto-create when this type is
# used in add_column (that auto-create is exactly the unsafe checkfirst
# path this fix replaces).
_REPLY_STATUS_ENUM = postgresql.ENUM(
    "positive", "negative", "neutral", "out_of_office", name="reply_status", create_type=False
)


def upgrade() -> None:
    # Idempotent under concurrent execution from multiple containers -
    # see migration docstring. Postgres has no CREATE TYPE IF NOT EXISTS,
    # so this catches the duplicate_object error a racing container's own
    # CREATE TYPE can raise, entirely inside Postgres, rather than
    # relying on an application-side existence check first.
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE reply_status AS ENUM ('positive', 'negative', 'neutral', 'out_of_office');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.add_column("conversations", sa.Column("reply_status", _REPLY_STATUS_ENUM, nullable=True))
    op.add_column("conversations", sa.Column("last_reply_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("last_reply_from", sa.String(length=255), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("needs_human_review", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_index("ix_conversations_reply_status", "conversations", ["reply_status"])
    op.create_index("ix_conversations_last_reply_at", "conversations", ["last_reply_at"])
    op.create_index("ix_conversations_needs_human_review", "conversations", ["needs_human_review"])


def downgrade() -> None:
    op.drop_index("ix_conversations_needs_human_review", table_name="conversations")
    op.drop_index("ix_conversations_last_reply_at", table_name="conversations")
    op.drop_index("ix_conversations_reply_status", table_name="conversations")

    op.drop_column("conversations", "needs_human_review")
    op.drop_column("conversations", "last_reply_from")
    op.drop_column("conversations", "last_reply_at")
    op.drop_column("conversations", "reply_status")

    # DROP TYPE IF EXISTS - Postgres supports IF EXISTS on DROP directly
    # (unlike CREATE), so no DO block is needed here.
    op.execute("DROP TYPE IF EXISTS reply_status")
