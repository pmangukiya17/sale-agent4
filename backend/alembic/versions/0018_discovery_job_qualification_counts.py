"""M8.8: per-job qualified/rejected prospect counts on discovery_jobs.

Live Workflow Visualization needs real, per-run "qualified buyers" /
"rejected buyers" counts (Discovery's own scoring pass already produces
these outcomes via _score_and_apply in app/discovery/pipeline.py - the
data was simply never persisted per-job before this). Additive-only:
two new NOT NULL integer columns with a server_default of 0, so every
existing discovery_jobs row (created before this migration) reads as
"0 qualified, 0 rejected" rather than requiring a backfill query - an
honest default for a run this feature didn't exist to measure, not a
fabricated number.

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "discovery_jobs",
        sa.Column("prospect_qualified_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "discovery_jobs",
        sa.Column("prospect_rejected_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("discovery_jobs", "prospect_rejected_count")
    op.drop_column("discovery_jobs", "prospect_qualified_count")
