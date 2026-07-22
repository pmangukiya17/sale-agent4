"""M8.15: real block count on outreach_jobs.

Live Workflow Visualization for Outreach needs a real "content blocks
generated" count - app/outreach/pipeline.py already computes
len(outcome.blocks) while assembling ai_generated_content, it was simply
never persisted per-job before this (identical situation, and identical
fix, to migrations 0018/0019/0020). Additive-only: one new NOT NULL
integer column with a server_default of 0.

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outreach_jobs",
        sa.Column("block_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("outreach_jobs", "block_count")
