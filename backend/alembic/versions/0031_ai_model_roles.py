"""M8.3 (AI Gateway Management & Control, Step 3 - Model Role Management):
ai_model_roles - one new table underneath a (new, this step)
DB-backed-with-code-fallback resolution layer in
app.ai_gateway.local_model_policy, read exclusively by
LocalOllamaProviderClient._resolve_model() (see that model's own
docstring for the full "local-tier only, never touches a cloud
ProviderClient" scope per CEO decision #2). A role_name with no row here
resolves exactly as it did before this migration - via the existing
hardcoded LOCAL_MODEL_ROLES settings-attribute indirection - so this
table is purely additive; no existing deployment behavior changes until
an operator explicitly saves a role through the (this step's) editor UI.

Zero changes to any existing table, column, constraint, or index.

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_model_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("role_name", sa.String(50), nullable=False),
        sa.Column("model", sa.String(150), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "updated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_unique_constraint("uq_ai_model_roles_role_name", "ai_model_roles", ["role_name"])
    op.create_index("ix_ai_model_roles_role_name", "ai_model_roles", ["role_name"])
    op.create_index("ix_ai_model_roles_updated_by_user_id", "ai_model_roles", ["updated_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_model_roles_updated_by_user_id", table_name="ai_model_roles")
    op.drop_index("ix_ai_model_roles_role_name", table_name="ai_model_roles")
    op.drop_constraint("uq_ai_model_roles_role_name", "ai_model_roles", type_="unique")
    op.drop_table("ai_model_roles")
