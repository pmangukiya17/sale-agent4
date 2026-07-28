"""M8.3 (AI Gateway Management & Control, Step 1): ai_provider_configs +
ai_provider_config_audits - two new tables underneath
app.ai_gateway.provider_config.resolve_provider_config(), the DB-backed
override layer sitting in front of the `.env`-sourced settings every
ProviderClient read directly through M8.2. A provider_key with no row in
ai_provider_configs behaves exactly as before this migration - both
tables are purely additive, zero effect on any deployment until an
operator explicitly saves a provider's configuration through the (future,
Step 2) UI.

ai_provider_config_audits is the CEO's explicit "lightweight configuration
audit history" refinement - who/when/what-changed, no rollback support,
no previous-full-snapshot column, append-only.

Zero changes to any existing table, column, constraint, or index.

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("provider_key", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("default_model", sa.String(150), nullable=True),
        sa.Column("extra_settings", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_unique_constraint("uq_ai_provider_configs_provider_key", "ai_provider_configs", ["provider_key"])
    op.create_index("ix_ai_provider_configs_provider_key", "ai_provider_configs", ["provider_key"])
    op.create_index("ix_ai_provider_configs_updated_by_user_id", "ai_provider_configs", ["updated_by_user_id"])

    op.create_table(
        "ai_provider_config_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_key", sa.String(50), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "changed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("field_changes", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_ai_provider_config_audits_provider_key", "ai_provider_config_audits", ["provider_key"])
    op.create_index("ix_ai_provider_config_audits_changed_at", "ai_provider_config_audits", ["changed_at"])
    op.create_index(
        "ix_ai_provider_config_audits_changed_by_user_id", "ai_provider_config_audits", ["changed_by_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_provider_config_audits_changed_by_user_id", table_name="ai_provider_config_audits")
    op.drop_index("ix_ai_provider_config_audits_changed_at", table_name="ai_provider_config_audits")
    op.drop_index("ix_ai_provider_config_audits_provider_key", table_name="ai_provider_config_audits")
    op.drop_table("ai_provider_config_audits")

    op.drop_index("ix_ai_provider_configs_updated_by_user_id", table_name="ai_provider_configs")
    op.drop_index("ix_ai_provider_configs_provider_key", table_name="ai_provider_configs")
    op.drop_constraint("uq_ai_provider_configs_provider_key", "ai_provider_configs", type_="unique")
    op.drop_table("ai_provider_configs")
