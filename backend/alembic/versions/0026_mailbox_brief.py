"""Track C5 (dashboard-capabilities-architecture-plan.md, Section 6):
Mailbox Brief - one new table, mailbox_briefs, storing every persisted
executive-summary snapshot a business explicitly generates. No enum
types this time: ai_provider/ai_model are plain strings, matching
ProviderConnection.provider_key's own "adding a provider is a code
change, never a migration" convention, per the CEO's explicit
provider-agnostic requirement for this track.

No raw email/message content is stored here - only the AI's generated
summary text and the numeric context (recommendations/statistics, both
JSONB) it was computed from, carrying forward the same privacy
constraint future-milestones.md note 9 originally specified for this
capability.

Zero changes to any existing table, column, constraint, or index -
purely additive, same discipline as every migration since 0002.

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mailbox_briefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ai_provider", sa.String(50), nullable=False),
        sa.Column("ai_model", sa.String(100), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("recommendations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("statistics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_mailbox_briefs_company_profile_id", "mailbox_briefs", ["company_profile_id"])
    op.create_index("ix_mailbox_briefs_generated_at", "mailbox_briefs", ["generated_at"])


def downgrade() -> None:
    op.drop_index("ix_mailbox_briefs_generated_at", table_name="mailbox_briefs")
    op.drop_index("ix_mailbox_briefs_company_profile_id", table_name="mailbox_briefs")
    op.drop_table("mailbox_briefs")
