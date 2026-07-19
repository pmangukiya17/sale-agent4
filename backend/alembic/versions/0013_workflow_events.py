"""M7.1 Workflow Engine Part 1, Phase 1: event infrastructure only.

Adds the `events` table - the entire input surface of the new,
domain-agnostic Workflow Engine (see docs/architecture/
m7-workflow-engine-plan.md and m7-workflow-engine-implementation-plan.md,
both approved before this migration was written). Nothing in this
migration references any workflow-definition/instance table - those
arrive in migration 0015 (Part 1, Phase 3) - `events` is deliberately
useful and independently testable in complete isolation first (Part 1,
Phase 1), via app.workflow_engine.events.publish_event(), with nothing
downstream consuming it yet.

Two indexes, matching the approved architecture's design exactly (no
extra, redundant single-column indexes):
  - (company_profile_id, event_type, occurred_at) - the eventual Event
    Dispatcher worker's own poll query.
  - (correlation_id) - explainability lookups ("show me everything in
    this business process").
Plus a unique index on sequence_no (a new-to-this-project BigInteger
Identity column - see the Event model's own docstring for why a plain
timestamp/UUID isn't sufficient as a total ordering key here) and a
plain index on subject_id (a cheap, direct "everything about this
entity" lookup).

Zero changes to any existing table, column, constraint, or index. Purely
additive, same discipline as every migration since 0002.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sequence_no", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("event_type", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "company_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject_type", sa.String(100), nullable=True),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_index("ix_events_sequence_no", "events", ["sequence_no"], unique=True)
    op.create_index("ix_events_subject_id", "events", ["subject_id"])
    op.create_index("ix_events_correlation_id", "events", ["correlation_id"])
    op.create_index(
        "ix_events_company_profile_id_event_type_occurred_at",
        "events",
        ["company_profile_id", "event_type", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_events_company_profile_id_event_type_occurred_at", table_name="events")
    op.drop_index("ix_events_correlation_id", table_name="events")
    op.drop_index("ix_events_subject_id", table_name="events")
    op.drop_index("ix_events_sequence_no", table_name="events")

    op.drop_table("events")
