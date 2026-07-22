"""CRM Automation: last_contacted_at/last_replied_at on Prospect and
ProspectContact, plus the new tasks table (Recommended Actions).

Deferred scope from docs/architecture/m6-reply-intelligence-plan.md
section 2/5, adjusted at approval time (see that document's own M6.5
entry and this migration's docstring below for the exact adjustments):

- Prospect.last_contacted_at/last_replied_at and the same two columns on
  ProspectContact were originally planned as part of M6.1 but never
  actually built then - this migration closes that real, pre-existing
  gap. Both nullable: a Prospect/ProspectContact never contacted or
  replied to simply has NULL, not a placeholder date.

- tasks: the persisted Recommended Action model. Two new enum types
  (task_priority: low/normal/high, task_status: pending/completed/
  dismissed). Deliberately NO reply_analysis_id column - the original
  doc's proposed FK target (a per-message ReplyAnalysis table) was
  explicitly rejected at M6.4's real approval and does not exist;
  provenance instead lives on source_event_type (a free string, e.g.
  "reply_classified"/"relationship_stage_advanced"). assigned_user_id is
  nullable and deliberately unused starting today - added now so the
  future M9 Organization & AI Workforce Management milestone needs zero
  migration to add task assignment later.

Zero changes to any existing column, constraint, or index. Purely
additive, same discipline as every migration since 0002. Enum types
created via the idempotent `DO $$ ... EXCEPTION WHEN duplicate_object`
block - see migration 0012's own docstring for why (concurrent
`alembic upgrade head` from five containers on this project's startup).

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TASK_PRIORITY_ENUM = postgresql.ENUM("low", "normal", "high", name="task_priority", create_type=False)
_TASK_STATUS_ENUM = postgresql.ENUM("pending", "completed", "dismissed", name="task_status", create_type=False)


def upgrade() -> None:
    # --- Prospect / ProspectContact: the real, pre-existing gap -----------
    op.add_column("prospects", sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("prospects", sa.Column("last_replied_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_prospects_last_contacted_at", "prospects", ["last_contacted_at"])
    op.create_index("ix_prospects_last_replied_at", "prospects", ["last_replied_at"])

    op.add_column("prospect_contacts", sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("prospect_contacts", sa.Column("last_replied_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_prospect_contacts_last_contacted_at", "prospect_contacts", ["last_contacted_at"])
    op.create_index("ix_prospect_contacts_last_replied_at", "prospect_contacts", ["last_replied_at"])

    # --- tasks: new enum types, idempotent under concurrent execution ------
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE task_priority AS ENUM ('low', 'normal', 'high');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE task_status AS ENUM ('pending', 'completed', 'dismissed');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospect_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("suggested_action", sa.Text(), nullable=False),
        sa.Column("source_event_type", sa.String(100), nullable=False),
        sa.Column("priority", _TASK_PRIORITY_ENUM, nullable=False, server_default="normal"),
        sa.Column("status", _TASK_STATUS_ENUM, nullable=False, server_default="pending"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tasks_company_profile_id", "tasks", ["company_profile_id"])
    op.create_index("ix_tasks_prospect_id", "tasks", ["prospect_id"])
    op.create_index("ix_tasks_prospect_contact_id", "tasks", ["prospect_contact_id"])
    op.create_index("ix_tasks_conversation_id", "tasks", ["conversation_id"])
    op.create_index("ix_tasks_assigned_user_id", "tasks", ["assigned_user_id"])
    op.create_index("ix_tasks_source_event_type", "tasks", ["source_event_type"])
    op.create_index("ix_tasks_priority", "tasks", ["priority"])
    op.create_index("ix_tasks_status", "tasks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_priority", table_name="tasks")
    op.drop_index("ix_tasks_source_event_type", table_name="tasks")
    op.drop_index("ix_tasks_assigned_user_id", table_name="tasks")
    op.drop_index("ix_tasks_conversation_id", table_name="tasks")
    op.drop_index("ix_tasks_prospect_contact_id", table_name="tasks")
    op.drop_index("ix_tasks_prospect_id", table_name="tasks")
    op.drop_index("ix_tasks_company_profile_id", table_name="tasks")
    op.drop_table("tasks")

    bind = op.get_bind()
    postgresql.ENUM(name="task_status", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="task_priority", create_type=False).drop(bind, checkfirst=True)

    op.drop_index("ix_prospect_contacts_last_replied_at", table_name="prospect_contacts")
    op.drop_index("ix_prospect_contacts_last_contacted_at", table_name="prospect_contacts")
    op.drop_column("prospect_contacts", "last_replied_at")
    op.drop_column("prospect_contacts", "last_contacted_at")

    op.drop_index("ix_prospects_last_replied_at", table_name="prospects")
    op.drop_index("ix_prospects_last_contacted_at", table_name="prospects")
    op.drop_column("prospects", "last_replied_at")
    op.drop_column("prospects", "last_contacted_at")
