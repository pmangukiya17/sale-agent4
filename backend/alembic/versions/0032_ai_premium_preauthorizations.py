"""M8.3 (AI Gateway Management & Control, Step 7 - Premium Approval UI):
ai_premium_preauthorizations - one new table implementing the CEO-approved
"pre-authorization, not pause/resume" model (see docs/architecture/m8-3-
ai-gateway-control-center-plan.md Section 12 Decision 1 and Section 13.1).
An admin's Approve/Reject decision against a flagged AIRequestLog row
writes exactly one row here - "approved" rows are a genuine, load-bearing
gate override (read by app.ai_gateway.premium_approval_resolver on
AIGateway's own decision path); "rejected" rows are audit-only. No existing
table, column, constraint, or index changes.

company_profile_id uses ondelete=RESTRICT (CEO decision, 2026-07-29):
pre-authorizations are governance/audit records, and deleting a company
while they exist must be an explicit administrative action, matching this
project's consistent RESTRICT-over-CASCADE posture (see the Track A "fix 7
CASCADE FKs to RESTRICT" migration this mirrors).

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_premium_preauthorizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "company_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("capability", sa.String(100), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column(
            "decided_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_request_log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_request_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_premium_preauthorizations_company_profile_id", "ai_premium_preauthorizations", ["company_profile_id"])
    op.create_index("ix_ai_premium_preauthorizations_capability", "ai_premium_preauthorizations", ["capability"])
    op.create_index(
        "ix_ai_premium_preauthorizations_decided_by_user_id", "ai_premium_preauthorizations", ["decided_by_user_id"]
    )
    op.create_index(
        "ix_ai_premium_preauthorizations_source_request_log_id",
        "ai_premium_preauthorizations",
        ["source_request_log_id"],
    )
    # The gate-check's own hot-path query (company_profile_id + capability +
    # decision="approved" + expires_at > now()) is the one that matters for
    # AIGateway.complete()'s per-request latency - a composite index on the
    # three equality-filtered columns it always uses together.
    op.create_index(
        "ix_ai_premium_preauthorizations_lookup",
        "ai_premium_preauthorizations",
        ["company_profile_id", "capability", "decision"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_premium_preauthorizations_lookup", table_name="ai_premium_preauthorizations")
    op.drop_index("ix_ai_premium_preauthorizations_source_request_log_id", table_name="ai_premium_preauthorizations")
    op.drop_index("ix_ai_premium_preauthorizations_decided_by_user_id", table_name="ai_premium_preauthorizations")
    op.drop_index("ix_ai_premium_preauthorizations_capability", table_name="ai_premium_preauthorizations")
    op.drop_index("ix_ai_premium_preauthorizations_company_profile_id", table_name="ai_premium_preauthorizations")
    op.drop_table("ai_premium_preauthorizations")
