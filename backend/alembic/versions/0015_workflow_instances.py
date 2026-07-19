"""M7.1 Workflow Engine Part 1, Phase 3: workflow_instances,
workflow_step_invocations, event_consumptions.

One migration, not three, because every table here has a real FK
dependency on another table also introduced in this same migration
(workflow_instances -> workflow_definitions [migration 0014, already
applied]; workflow_step_invocations -> workflow_instances;
event_consumptions -> both events [migration 0013, already applied] AND
workflow_instances) - splitting further would only produce intermediate
states with dangling FKs, not genuinely independent review points,
matching the exact reasoning migration 0009 used for the same situation.

Deliberately does NOT include workflow_timers - that table exists in the
approved architecture (docs/architecture/m7-workflow-engine-plan.md
section 7) but has no consumer anywhere in Part 1 of the implementation
plan (the pilot workflow, arriving in a later phase, only ever waits on
events, never on a timeout) - adding it now would be exactly the
anticipatory-schema mistake this project has repeatedly walked back
elsewhere (see e.g. email_messages' own is_analyzed/attempt_count
history). It arrives as a small, additive migration whenever a real
consumer actually needs it, matching this project's "add columns/tables
when the consuming phase needs them" discipline.

Three new enum types (workflow_instance_status,
workflow_step_invocation_status, event_consumption_outcome), all created
via the same idempotent DO-block pattern as migration 0014.

Key constraints:
  - workflow_instances(status, company_profile_id) - the Step Runner
    worker's own claim query (Part 1, Phase 5).
  - UniqueConstraint(event_id, workflow_instance_id) on
    event_consumptions - the idempotency guarantee from the approved
    architecture (see that model's own docstring for the documented,
    accepted NULL-instance edge case this constraint does NOT cover, and
    why that gap is harmless).

Zero changes to any existing table, column, constraint, or index. Purely
additive, same discipline as every migration since 0002.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WORKFLOW_INSTANCE_STATUS_ENUM = postgresql.ENUM(
    "pending", "running", "waiting", "suspended", "completed", "failed", "cancelled",
    name="workflow_instance_status", create_type=False,
)
_WORKFLOW_STEP_INVOCATION_STATUS_ENUM = postgresql.ENUM(
    "pending", "running", "succeeded", "failed", "skipped",
    name="workflow_step_invocation_status", create_type=False,
)
_EVENT_CONSUMPTION_OUTCOME_ENUM = postgresql.ENUM(
    "started_new_instance", "resumed_instance", "no_match",
    name="event_consumption_outcome", create_type=False,
)


def upgrade() -> None:
    # Idempotent under concurrent execution from multiple containers -
    # see migration 0012's docstring for the full reasoning.
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE workflow_instance_status AS ENUM
                ('pending', 'running', 'waiting', 'suspended', 'completed', 'failed', 'cancelled');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE workflow_step_invocation_status AS ENUM
                ('pending', 'running', 'succeeded', 'failed', 'skipped');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE event_consumption_outcome AS ENUM
                ('started_new_instance', 'resumed_instance', 'no_match');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    # --- workflow_instances --------------------------------------------
    op.create_table(
        "workflow_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "workflow_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_definitions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "company_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject_type", sa.String(100), nullable=True),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", _WORKFLOW_INSTANCE_STATUS_ENUM, nullable=False, server_default="pending"),
        sa.Column("current_step_id", sa.String(255), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("claimed_by", sa.String(255), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workflow_instances_workflow_definition_id", "workflow_instances", ["workflow_definition_id"])
    op.create_index("ix_workflow_instances_company_profile_id", "workflow_instances", ["company_profile_id"])
    op.create_index("ix_workflow_instances_subject_id", "workflow_instances", ["subject_id"])
    op.create_index("ix_workflow_instances_status", "workflow_instances", ["status"])
    # The Step Runner's own claim query - see that worker's docstring
    # (Part 1, Phase 5).
    op.create_index(
        "ix_workflow_instances_status_company_profile_id", "workflow_instances", ["status", "company_profile_id"]
    )

    # --- workflow_step_invocations --------------------------------------
    op.create_table(
        "workflow_step_invocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "workflow_instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_id", sa.String(255), nullable=False),
        sa.Column("action_key", sa.String(255), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", _WORKFLOW_STEP_INVOCATION_STATUS_ENUM, nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("output", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_workflow_step_invocations_workflow_instance_id", "workflow_step_invocations", ["workflow_instance_id"]
    )
    op.create_index("ix_workflow_step_invocations_status", "workflow_step_invocations", ["status"])

    # --- event_consumptions -----------------------------------------------
    op.create_table(
        "event_consumptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "workflow_instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_instances.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("outcome", _EVENT_CONSUMPTION_OUTCOME_ENUM, nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "workflow_instance_id", name="uq_event_consumptions_event_instance"),
    )
    op.create_index("ix_event_consumptions_event_id", "event_consumptions", ["event_id"])
    op.create_index("ix_event_consumptions_workflow_instance_id", "event_consumptions", ["workflow_instance_id"])


def downgrade() -> None:
    op.drop_index("ix_event_consumptions_workflow_instance_id", table_name="event_consumptions")
    op.drop_index("ix_event_consumptions_event_id", table_name="event_consumptions")
    op.drop_table("event_consumptions")

    op.drop_index("ix_workflow_step_invocations_status", table_name="workflow_step_invocations")
    op.drop_index("ix_workflow_step_invocations_workflow_instance_id", table_name="workflow_step_invocations")
    op.drop_table("workflow_step_invocations")

    op.drop_index("ix_workflow_instances_status_company_profile_id", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_status", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_subject_id", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_company_profile_id", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_workflow_definition_id", table_name="workflow_instances")
    op.drop_table("workflow_instances")

    op.execute("DROP TYPE IF EXISTS event_consumption_outcome")
    op.execute("DROP TYPE IF EXISTS workflow_step_invocation_status")
    op.execute("DROP TYPE IF EXISTS workflow_instance_status")
