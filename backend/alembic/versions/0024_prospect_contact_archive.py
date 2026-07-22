"""ProspectContact archive lifecycle: is_archived/archived_at/archived_by_user_id.

Approved alongside migration 0023's RESTRICT fix on this entity's
execution-history FKs (delivery_queue_items, outreach_drafts/requests/
jobs/runs). Per the CEO's explicit direction: "ProspectContact should
follow the same philosophy as Prospect: archive instead of delete,
preserve history, hide archived contacts by default, allow hard delete
only when no execution history exists" - and this is now written into
docs/architecture/deferred-items-and-design-boundaries.md as the
platform-wide lifecycle rule for any entity that participates in
execution history, not just this one.

Three new nullable-safe, purely additive columns on prospect_contacts:
- is_archived: bool, default False, indexed (list views filter on it)
- archived_at: nullable timestamp
- archived_by_user_id: nullable FK to users, ON DELETE SET NULL (matches
  Prospect.reviewed_by_user_id's existing pattern - losing the user
  record shouldn't erase that the contact was archived, just who did it)

Zero changes to any existing column, constraint, or index. is_archived
keeps its server_default('false') after backfilling existing rows,
matching this project's standing convention of leaving additive-column
server defaults in place (e.g. migration 0021's block_count) rather than
dropping them post-backfill.

Migration 0023 already made hard delete safe (RESTRICT); this migration
adds the preferred, non-destructive path on top of it. The
archive/unarchive API routes and the list-view default filter are a
separate, API-layer commit.

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "prospect_contacts",
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_prospect_contacts_is_archived", "prospect_contacts", ["is_archived"])
    op.add_column(
        "prospect_contacts",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "prospect_contacts",
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "prospect_contacts_archived_by_user_id_fkey",
        "prospect_contacts",
        "users",
        ["archived_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("prospect_contacts_archived_by_user_id_fkey", "prospect_contacts", type_="foreignkey")
    op.drop_column("prospect_contacts", "archived_by_user_id")
    op.drop_column("prospect_contacts", "archived_at")
    op.drop_index("ix_prospect_contacts_is_archived", "prospect_contacts")
    op.drop_column("prospect_contacts", "is_archived")
