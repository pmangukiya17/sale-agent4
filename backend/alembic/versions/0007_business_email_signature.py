"""Business Branding (M4 Finalization): brand_email_signatures. A single
mutable 1:1 row per business holding its rich-HTML email signature.
Deliberately NOT a "business_brandings" aggregate table - this hangs
directly off company_profile_id, the same way products/icp_criteria/
knowledge_base already do. Deliberately NOT versioned like outreach
playbooks/prompt_versions - it is business configuration, edited in place.
Explainability for historical drafts is preserved separately, by freezing
the rendered signature_html into outreach_drafts.ai_generated_content at
generation time (no schema change to outreach_drafts required).

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brand_email_signatures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "company_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signature_html", sa.Text(), nullable=True),
        sa.Column("signature_plain_text", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("company_profile_id", name="uq_brand_email_signatures_company_profile_id"),
    )
    op.create_index(
        "ix_brand_email_signatures_company_profile_id",
        "brand_email_signatures",
        ["company_profile_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_brand_email_signatures_company_profile_id", table_name="brand_email_signatures")
    op.drop_table("brand_email_signatures")
