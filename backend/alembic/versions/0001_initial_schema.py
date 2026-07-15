"""initial CRM schema

Revision ID: 0001
Revises:
Create Date: 2026-07-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # create_type=False is deliberate: without it, Postgres ENUM columns
    # register a `before_create` hook on their owning table that re-issues
    # CREATE TYPE the moment op.create_table() runs (Alembic fires that hook
    # with checkfirst=False), which collides with the explicit .create()
    # calls below and raises "type already exists" on a clean database.
    # Setting create_type=False disables that automatic lifecycle so the
    # explicit create()/drop() calls in this migration are the only place
    # the type is ever created or dropped.
    user_role = postgresql.ENUM("admin", "operator", name="user_role", create_type=False)
    pipeline_stage = postgresql.ENUM(
        "discovered", "enriched", "verified", "website_analyzed", "qualified",
        "disqualified", "contact_found", "draft_generated", "pending_approval",
        "sent", "replied", "no_reply", "follow_up_1", "follow_up_2", "follow_up_3",
        "won", "lost", "nurture", name="pipeline_stage", create_type=False,
    )
    message_direction = postgresql.ENUM(
        "outbound", "inbound", name="message_direction", create_type=False
    )
    followup_status = postgresql.ENUM(
        "scheduled", "sent", "cancelled", name="followup_status", create_type=False
    )

    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)
    pipeline_stage.create(bind, checkfirst=True)
    message_direction.create(bind, checkfirst=True)
    followup_status.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", user_role, nullable=False, server_default="operator"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("legitimacy_score", sa.Float(), nullable=True),
        sa.Column("icp_score", sa.Float(), nullable=True),
        sa.Column("stage", pipeline_stage, nullable=False, server_default="discovered"),
        sa.Column("notes", sa.String(2000), nullable=True),
    )
    op.create_index("ix_companies_name", "companies", ["name"])
    op.create_index("ix_companies_stage", "companies", ["stage"])

    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
    )
    op.create_index("ix_contacts_company_id", "contacts", ["company_id"])
    op.create_index("ix_contacts_email", "contacts", ["email"])

    op.create_table(
        "website_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_scrape_ref", sa.String(500), nullable=True),
        sa.Column("structured_summary", postgresql.JSONB(), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_website_findings_company_id", "website_findings", ["company_id"])

    op.create_table(
        "icp_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("outlook_conversation_id", sa.String(500), nullable=True),
    )
    op.create_index("ix_threads_company_id", "threads", ["company_id"])
    op.create_index("ix_threads_outlook_conversation_id", "threads", ["outlook_conversation_id"])

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", message_direction, nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("outlook_message_id", sa.String(500), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("classification", sa.String(100), nullable=True),
    )
    op.create_index("ix_messages_thread_id", "messages", ["thread_id"])

    op.create_table(
        "followups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("threads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cadence_step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", followup_status, nullable=False, server_default="scheduled"),
        sa.Column("stop_reason", sa.String(255), nullable=True),
    )
    op.create_index("ix_followups_company_id", "followups", ["company_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("followups")
    op.drop_table("messages")
    op.drop_table("threads")
    op.drop_table("icp_criteria")
    op.drop_table("website_findings")
    op.drop_table("contacts")
    op.drop_table("companies")
    op.drop_table("users")

    # Tables must be dropped before their enum types (Postgres refuses to
    # drop a type that a column still references). create_type=False here
    # too, purely for symmetry with upgrade() — these objects are only ever
    # used for their .drop() call, never attached to a column.
    bind = op.get_bind()
    postgresql.ENUM(name="followup_status", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="message_direction", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="pipeline_stage", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="user_role", create_type=False).drop(bind, checkfirst=True)
