"""M8.10: per-job signal/recommendation counts on research_jobs.

Live Workflow Visualization for Research needs real, per-run "signals
found" / "recommendations generated" counts - app/research/pipeline.py
already computes signal_count/recommendation_count as local variables
while building the IntelligenceSnapshot, they were simply never persisted
per-job before this (identical situation, and identical fix, to
migration 0018's discovery_jobs.prospect_qualified_count/
prospect_rejected_count). Additive-only: two new NOT NULL integer
columns with a server_default of 0, so every existing research_jobs row
reads as "0 signals, 0 recommendations" rather than requiring a backfill
query.

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "research_jobs",
        sa.Column("signal_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "research_jobs",
        sa.Column("recommendation_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("research_jobs", "recommendation_count")
    op.drop_column("research_jobs", "signal_count")
