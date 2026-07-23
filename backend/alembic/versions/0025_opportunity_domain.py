"""Track C3 (dashboard-capabilities-architecture-plan.md, Section 1):
Opportunity domain - the platform's first real, monetary sales-deal
model. Two new tables (opportunities, opportunity_stage_history) and two
new enum types (opportunity_stage, opportunity_forecast_category).

opportunities is AI-ready from day one per the CEO's explicit direction:
win_probability, ai_confidence_score, forecast_category, ai_reasoning,
and next_recommended_action all exist as real, nullable columns now even
though no AI engine populates them yet - same "additive, not a schema
fight" bet Task.assigned_user_id/OutreachContext already made for their
own future milestones. estimated_revenue/actual_revenue are separate
NUMERIC(14,2) columns (real money, not Float) rather than one "amount"
field, per the CEO's own wording.

opportunity_stage_history is the append-only authority for every stage
transition (including creation) - per the CEO's explicit direction, an
Opportunity MAY skip stages and this platform does NOT enforce a linear
workflow, so this table (not an assumed path through the enum's order)
is what any funnel/conversion-rate/stage-duration report must read from.

opportunities.id is RESTRICT-protected from the start via
opportunity_stage_history's own FK (ON DELETE CASCADE on the history
table itself is correct - deleting an Opportunity should take its own
history with it - but the API-level delete route is what enforces
"don't hard-delete an Opportunity that has any real stage history,"
mirroring the ProspectContact/DiscoverySearch RESTRICT precedent
documented in deferred-items-and-design-boundaries.md; see this
migration's own opportunities table below for the actual FK direction).

Zero changes to any existing table, column, constraint, or index -
purely additive, same discipline as every migration since 0002. Enum
types created via the idempotent `DO $$ ... EXCEPTION WHEN
duplicate_object` block - see migration 0012's own docstring for why
(concurrent `alembic upgrade head` from multiple containers on this
project's startup).

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OPPORTUNITY_STAGE_VALUES = (
    "qualified_lead",
    "meeting",
    "sample",
    "quotation",
    "negotiation",
    "purchase_order",
    "closed_won",
    "closed_lost",
)
_OPPORTUNITY_FORECAST_CATEGORY_VALUES = ("pipeline", "best_case", "commit", "closed")

_OPPORTUNITY_STAGE_ENUM = postgresql.ENUM(*_OPPORTUNITY_STAGE_VALUES, name="opportunity_stage", create_type=False)
_OPPORTUNITY_FORECAST_CATEGORY_ENUM = postgresql.ENUM(
    *_OPPORTUNITY_FORECAST_CATEGORY_VALUES, name="opportunity_forecast_category", create_type=False
)


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE opportunity_stage AS ENUM (
                'qualified_lead', 'meeting', 'sample', 'quotation',
                'negotiation', 'purchase_order', 'closed_won', 'closed_lost'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE opportunity_forecast_category AS ENUM (
                'pipeline', 'best_case', 'commit', 'closed'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.create_table(
        "opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospect_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("stage", _OPPORTUNITY_STAGE_ENUM, nullable=False, server_default="qualified_lead"),
        sa.Column("estimated_revenue", sa.Numeric(14, 2), nullable=True),
        sa.Column("actual_revenue", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("win_probability", sa.Float(), nullable=True),
        sa.Column("ai_confidence_score", sa.Float(), nullable=True),
        sa.Column("forecast_category", _OPPORTUNITY_FORECAST_CATEGORY_ENUM, nullable=True),
        sa.Column("ai_reasoning", sa.Text(), nullable=True),
        sa.Column("next_recommended_action", sa.Text(), nullable=True),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lost_reason", sa.String(500), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_opportunities_company_profile_id", "opportunities", ["company_profile_id"])
    op.create_index("ix_opportunities_prospect_id", "opportunities", ["prospect_id"])
    op.create_index("ix_opportunities_prospect_contact_id", "opportunities", ["prospect_contact_id"])
    op.create_index("ix_opportunities_stage", "opportunities", ["stage"])
    op.create_index("ix_opportunities_forecast_category", "opportunities", ["forecast_category"])
    op.create_index("ix_opportunities_owner_user_id", "opportunities", ["owner_user_id"])
    op.create_index("ix_opportunities_source_task_id", "opportunities", ["source_task_id"])

    op.create_table(
        "opportunity_stage_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_stage", _OPPORTUNITY_STAGE_ENUM, nullable=True),
        sa.Column("to_stage", _OPPORTUNITY_STAGE_ENUM, nullable=False),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_opportunity_stage_history_opportunity_id", "opportunity_stage_history", ["opportunity_id"])


def downgrade() -> None:
    op.drop_index("ix_opportunity_stage_history_opportunity_id", table_name="opportunity_stage_history")
    op.drop_table("opportunity_stage_history")

    op.drop_index("ix_opportunities_source_task_id", table_name="opportunities")
    op.drop_index("ix_opportunities_owner_user_id", table_name="opportunities")
    op.drop_index("ix_opportunities_forecast_category", table_name="opportunities")
    op.drop_index("ix_opportunities_stage", table_name="opportunities")
    op.drop_index("ix_opportunities_prospect_contact_id", table_name="opportunities")
    op.drop_index("ix_opportunities_prospect_id", table_name="opportunities")
    op.drop_index("ix_opportunities_company_profile_id", table_name="opportunities")
    op.drop_table("opportunities")

    bind = op.get_bind()
    postgresql.ENUM(name="opportunity_forecast_category", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="opportunity_stage", create_type=False).drop(bind, checkfirst=True)
