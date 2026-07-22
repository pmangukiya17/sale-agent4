"""M8.11: real strategy count on personalization_jobs.

Live Workflow Visualization for Personalization needs a real "strategies
generated" count - app/personalization/pipeline.py already computes
len(outcome.strategies) while building PersonalizationSnapshot rows, it
was simply never persisted per-job before this (identical situation, and
identical fix, to migrations 0018/0019). Additive-only: one new NOT NULL
integer column with a server_default of 0.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "personalization_jobs",
        sa.Column("strategy_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("personalization_jobs", "strategy_count")
