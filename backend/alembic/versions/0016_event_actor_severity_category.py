"""M8.5 Event Backbone: extend the existing `events` table.

Adds four nullable columns to the platform's single Event stream
(app.models.workflow_event.Event, created in migration 0013) -
actor_type, actor_id, severity, category. Deliberately NOT a new table:
per the approved M8.5 architecture, there is exactly one platform Event
stream, and every future AI module publishes into it via the existing
app.workflow_engine.events.publish_event() helper. See that model's own
docstring (updated alongside this migration) for what each column means.

Zero changes to sequence_no, existing indexes, the events table's
existing columns, or any Workflow Engine matching/consumption logic
(event_dispatcher_worker.py, step_runner_worker.py, EventConsumption) -
this is a pure additive schema change, same discipline as every
migration since 0002.

`category` gets its own index (filtering/grouping is exactly what it's
for, per the M8.5 brief - "dashboard grouping and future observability").
actor_type/actor_id/severity are not indexed here - no query in this
milestone filters by them yet; an index can be added later, additively,
if/when one does.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("actor_type", sa.String(50), nullable=True))
    op.add_column("events", sa.Column("actor_id", sa.String(255), nullable=True))
    op.add_column("events", sa.Column("severity", sa.String(50), nullable=True))
    op.add_column("events", sa.Column("category", sa.String(100), nullable=True))
    op.create_index("ix_events_category", "events", ["category"])


def downgrade() -> None:
    op.drop_index("ix_events_category", table_name="events")
    op.drop_column("events", "category")
    op.drop_column("events", "severity")
    op.drop_column("events", "actor_id")
    op.drop_column("events", "actor_type")
