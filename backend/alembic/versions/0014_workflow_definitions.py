"""M7.1 Workflow Engine Part 1, Phase 2: workflow_definitions only.

Adds the `workflow_definitions` table and its `workflow_definition_status`
enum type (DRAFT/ACTIVE/DEPRECATED - see app.models.enums.
WorkflowDefinitionStatus's own docstring for the full lifecycle this
implements). Deliberately its own migration, not bundled with Part 1
Phase 3's workflow_instances/workflow_step_invocations/
event_consumptions - `workflow_definitions` has no FK dependency on any
of those tables (the dependency runs the other way: instances will FK to
definitions in migration 0015), so it is fully independently reviewable
and testable on its own first, matching the phase split in the approved
implementation plan.

Enum type created via the same idempotent DO-block pattern migration
0012 was corrected to use (see that migration's own docstring for the
full concurrent-container-boot race this avoids) - not the
checkfirst=True pattern from migration 0009, which is what caused that
earlier bug. Applied here from the start rather than needing a follow-up
fix.

Two constraints, both matching the approved architecture exactly:
  - UniqueConstraint(key, version) - two rows can never claim the same
    version number for the same key.
  - Partial unique index on (key) WHERE status = 'active' - at most one
    ACTIVE version per key, enforced at the database level, not only by
    the app.workflow_engine.definitions service layer. Direct precedent
    for this exact shape already exists in this codebase (the partial
    unique dedup index on email_messages.internet_message_id, M6.1).

Zero changes to any existing table, column, constraint, or index. Purely
additive, same discipline as every migration since 0002.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WORKFLOW_DEFINITION_STATUS_ENUM = postgresql.ENUM(
    "draft", "active", "deprecated", name="workflow_definition_status", create_type=False
)


def upgrade() -> None:
    # Idempotent under concurrent execution from multiple containers -
    # see migration 0012's docstring for the full reasoning. Postgres has
    # no CREATE TYPE IF NOT EXISTS, so this catches the duplicate_object
    # error a racing container's own CREATE TYPE can raise, entirely
    # inside Postgres.
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE workflow_definition_status AS ENUM ('draft', 'active', 'deprecated');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.create_table(
        "workflow_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", _WORKFLOW_DEFINITION_STATUS_ENUM, nullable=False, server_default="draft"),
        sa.Column("trigger_event_type", sa.String(255), nullable=False),
        sa.Column("trigger_filter", postgresql.JSONB(), nullable=True),
        sa.Column("step_graph", postgresql.JSONB(), nullable=False),
        sa.Column(
            "company_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_profiles.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.UniqueConstraint("key", "version", name="uq_workflow_definitions_key_version"),
    )

    op.create_index("ix_workflow_definitions_key", "workflow_definitions", ["key"])
    op.create_index("ix_workflow_definitions_status", "workflow_definitions", ["status"])
    op.create_index("ix_workflow_definitions_company_profile_id", "workflow_definitions", ["company_profile_id"])

    # The at-most-one-ACTIVE-per-key invariant, enforced at the database
    # level.
    op.create_index(
        "uq_workflow_definitions_key_active",
        "workflow_definitions",
        ["key"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_workflow_definitions_key_active", table_name="workflow_definitions")
    op.drop_index("ix_workflow_definitions_company_profile_id", table_name="workflow_definitions")
    op.drop_index("ix_workflow_definitions_status", table_name="workflow_definitions")
    op.drop_index("ix_workflow_definitions_key", table_name="workflow_definitions")

    op.drop_table("workflow_definitions")

    op.execute("DROP TYPE IF EXISTS workflow_definition_status")
