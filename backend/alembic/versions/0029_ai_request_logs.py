"""M8.2 (AI Gateway Backend Integration): ai_request_logs - one new table,
durably persisting every AI Gateway call `app.ai_gateway.client.AIGateway`
already logs via `log_ai_request()`. `app.ai_gateway.request_log`'s own
docstring anticipated exactly this migration ("A future migration can add
an ai_request_logs table and swap log_ai_request()'s body to also INSERT
a row - callers of this function never need to change").

company_profile_id/user_id are both nullable with ondelete="SET NULL" -
a historical observability record, not a business entity with its own
delete lifecycle; deleting a CompanyProfile/User should never be blocked
by, or silently destroy, its old AI request logs.

Zero changes to any existing table, column, constraint, or index - purely
additive, same discipline as every migration since 0002.

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_request_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capability", sa.String(100), nullable=False),
        sa.Column("provider_key", sa.String(50), nullable=True),
        sa.Column("model", sa.String(150), nullable=True),
        sa.Column("tier", sa.String(20), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column(
            "company_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
    )
    op.create_index("ix_ai_request_logs_occurred_at", "ai_request_logs", ["occurred_at"])
    op.create_index("ix_ai_request_logs_capability", "ai_request_logs", ["capability"])
    op.create_index("ix_ai_request_logs_provider_key", "ai_request_logs", ["provider_key"])
    op.create_index("ix_ai_request_logs_error_type", "ai_request_logs", ["error_type"])
    op.create_index("ix_ai_request_logs_company_profile_id", "ai_request_logs", ["company_profile_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_request_logs_company_profile_id", table_name="ai_request_logs")
    op.drop_index("ix_ai_request_logs_error_type", table_name="ai_request_logs")
    op.drop_index("ix_ai_request_logs_provider_key", table_name="ai_request_logs")
    op.drop_index("ix_ai_request_logs_capability", table_name="ai_request_logs")
    op.drop_index("ix_ai_request_logs_occurred_at", table_name="ai_request_logs")
    op.drop_table("ai_request_logs")
