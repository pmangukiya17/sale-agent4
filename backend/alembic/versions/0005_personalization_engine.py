"""M3 AI Personalization Engine: personalization templates, requests, jobs,
runs, snapshots, communication strategies, ranked strategies, evidence.
Also extends recommendation_type with call_to_action and adds a live
relationship_stage field to prospects.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-17

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- extend the existing recommendation_type enum (M2) ------------------
    # ALTER TYPE ... ADD VALUE cannot run inside the same transaction as
    # other DDL/DML that might use the new value (pre-PG12 rule; PG12+
    # relaxed this but Alembic still wraps migrations in a transaction by
    # default) - autocommit_block() runs this statement in its own
    # standalone transaction, the standard Alembic pattern for this.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE recommendation_type ADD VALUE IF NOT EXISTS 'call_to_action'")

    # --- new enum types -------------------------------------------------------
    personalization_job_status = postgresql.ENUM(
        "pending", "running", "completed", "failed", "cancelled",
        name="personalization_job_status", create_type=False,
    )
    buyer_readiness_level = postgresql.ENUM(
        "unknown", "low", "medium", "high", "ready_to_engage",
        name="buyer_readiness_level", create_type=False,
    )
    relationship_stage = postgresql.ENUM(
        "cold", "contacted", "engaged", "qualified", "negotiation",
        name="relationship_stage", create_type=False,
    )
    personalization_strategy_rank = postgresql.ENUM(
        "primary", "secondary", "fallback",
        name="personalization_strategy_rank", create_type=False,
    )
    communication_formality = postgresql.ENUM(
        "casual", "neutral", "formal",
        name="communication_formality", create_type=False,
    )
    communication_intensity_level = postgresql.ENUM(
        "low", "medium", "high",
        name="communication_intensity_level", create_type=False,
    )
    communication_length = postgresql.ENUM(
        "short", "medium", "long",
        name="communication_length", create_type=False,
    )

    for enum_type in (
        personalization_job_status, buyer_readiness_level, relationship_stage,
        personalization_strategy_rank, communication_formality,
        communication_intensity_level, communication_length,
    ):
        enum_type.create(bind, checkfirst=True)

    # --- prospects: add the live, mutable relationship_stage column --------
    op.add_column(
        "prospects",
        sa.Column("relationship_stage", relationship_stage, nullable=False, server_default="cold"),
    )
    op.create_index("ix_prospects_relationship_stage", "prospects", ["relationship_stage"])

    # --- personalization_templates: mirrors research_templates (0004) ------
    op.create_table(
        "personalization_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("personalization_spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_system_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_personalization_templates_company_profile_id", "personalization_templates", ["company_profile_id"])

    # --- personalization_requests: Template -> Request -> Job ---------------
    op.create_table(
        "personalization_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("personalization_template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_focus_areas", postgresql.JSONB(), nullable=True),
        sa.Column("status", personalization_job_status, nullable=False, server_default="pending"),
    )
    op.create_index("ix_personalization_requests_prospect_id", "personalization_requests", ["prospect_id"])
    op.create_index("ix_personalization_requests_company_profile_id", "personalization_requests", ["company_profile_id"])
    op.create_index("ix_personalization_requests_personalization_template_id", "personalization_requests", ["personalization_template_id"])
    op.create_index("ix_personalization_requests_status", "personalization_requests", ["status"])

    # --- personalization_jobs: one synchronous execution --------------------
    op.create_table(
        "personalization_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("personalization_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", personalization_job_status, nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("log", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_personalization_jobs_personalization_request_id", "personalization_jobs", ["personalization_request_id"])
    op.create_index("ix_personalization_jobs_prospect_id", "personalization_jobs", ["prospect_id"])
    op.create_index("ix_personalization_jobs_company_profile_id", "personalization_jobs", ["company_profile_id"])
    op.create_index("ix_personalization_jobs_status", "personalization_jobs", ["status"])

    # --- personalization_runs: frozen config snapshot -----------------------
    op.create_table(
        "personalization_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("personalization_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("personalization_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("personalization_version_created", sa.Integer(), nullable=True),
        sa.UniqueConstraint("personalization_job_id"),
    )
    op.create_index("ix_personalization_runs_personalization_request_id", "personalization_runs", ["personalization_request_id"])
    op.create_index("ix_personalization_runs_prospect_id", "personalization_runs", ["prospect_id"])
    op.create_index("ix_personalization_runs_company_profile_id", "personalization_runs", ["company_profile_id"])

    # --- personalization_snapshots: versioned, never overwritten ------------
    op.create_table(
        "personalization_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("personalization_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("buyer_persona", postgresql.JSONB(), nullable=True),
        sa.Column("buyer_readiness", buyer_readiness_level, nullable=False, server_default="unknown"),
        sa.Column("buyer_readiness_reasoning", sa.Text(), nullable=True),
        sa.Column("relationship_stage_at_generation", relationship_stage, nullable=False),
        sa.Column("personalization_variables", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_personalization_snapshots_prospect_id", "personalization_snapshots", ["prospect_id"])
    op.create_index("ix_personalization_snapshots_personalization_job_id", "personalization_snapshots", ["personalization_job_id"])
    op.create_index("ix_personalization_snapshots_company_profile_id", "personalization_snapshots", ["company_profile_id"])
    op.create_index("ix_personalization_snapshots_is_current", "personalization_snapshots", ["is_current"])
    op.create_index("ix_personalization_snapshots_buyer_readiness", "personalization_snapshots", ["buyer_readiness"])

    # --- communication_strategies: 1:1 communication blueprint --------------
    op.create_table(
        "communication_strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("personalization_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("formality", communication_formality, nullable=False),
        sa.Column("directness", communication_intensity_level, nullable=False),
        sa.Column("warmth", communication_intensity_level, nullable=False),
        sa.Column("technical_depth", communication_intensity_level, nullable=False),
        sa.Column("authority", communication_intensity_level, nullable=False),
        sa.Column("consultative_level", communication_intensity_level, nullable=False),
        sa.Column("urgency", communication_intensity_level, nullable=False),
        sa.Column("message_length", communication_length, nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.UniqueConstraint("personalization_snapshot_id"),
    )

    # --- personalization_strategies: up to 3 ranked approaches per snapshot -
    op.create_table(
        "personalization_strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("personalization_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("strategy_rank", personalization_strategy_rank, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.UniqueConstraint("personalization_snapshot_id", "strategy_rank", name="uq_personalization_strategy_rank"),
    )
    op.create_index("ix_personalization_strategies_personalization_snapshot_id", "personalization_strategies", ["personalization_snapshot_id"])

    # --- personalization_evidence: references Signal/Recommendation/-------
    # IntelligenceSnapshot only, never RawDocument - Research owns raw
    # evidence, Personalization owns strategy evidence.
    op.create_table(
        "personalization_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("personalization_strategy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_strategies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("signals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("intelligence_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("intelligence_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
    )
    op.create_index("ix_personalization_evidence_personalization_strategy_id", "personalization_evidence", ["personalization_strategy_id"])
    op.create_index("ix_personalization_evidence_signal_id", "personalization_evidence", ["signal_id"])
    op.create_index("ix_personalization_evidence_recommendation_id", "personalization_evidence", ["recommendation_id"])

    # --- seed data: system starter templates --------------------------------
    personalization_templates_table = sa.table(
        "personalization_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("company_profile_id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("personalization_spec", postgresql.JSONB),
        sa.column("is_system_default", sa.Boolean),
    )
    system_templates = [
        (
            "Standard Strategy Synthesis",
            "Balanced read of the current Intelligence Snapshot, Signals, and Recommendations - primary + fallback strategy.",
            {"focus_areas": ["buyer_persona", "communication_strategy", "strategy"], "always_produce_fallback": True},
        ),
        (
            "High-Readiness Fast Track",
            "For prospects already showing strong buying signals - emphasizes urgency and a direct call-to-action.",
            {"focus_areas": ["buyer_readiness", "strategy"], "always_produce_fallback": False},
        ),
        (
            "Early-Stage Relationship Building",
            "For cold, low-signal prospects - consultative tone, longer-form value-first approach.",
            {"focus_areas": ["communication_strategy", "buyer_persona"], "always_produce_fallback": True},
        ),
    ]
    op.bulk_insert(
        personalization_templates_table,
        [
            {
                "id": uuid.uuid4(),
                "company_profile_id": None,
                "name": name,
                "description": description,
                "personalization_spec": personalization_spec,
                "is_system_default": True,
            }
            for name, description, personalization_spec in system_templates
        ],
    )


def downgrade() -> None:
    op.drop_table("personalization_evidence")
    op.drop_table("personalization_strategies")
    op.drop_table("communication_strategies")
    op.drop_table("personalization_snapshots")
    op.drop_table("personalization_runs")
    op.drop_table("personalization_jobs")
    op.drop_table("personalization_requests")
    op.drop_table("personalization_templates")

    op.drop_index("ix_prospects_relationship_stage", table_name="prospects")
    op.drop_column("prospects", "relationship_stage")

    bind = op.get_bind()
    postgresql.ENUM(name="communication_length", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="communication_intensity_level", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="communication_formality", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="personalization_strategy_rank", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="relationship_stage", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="buyer_readiness_level", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="personalization_job_status", create_type=False).drop(bind, checkfirst=True)

    # NOTE: Postgres has no ALTER TYPE ... DROP VALUE. Removing
    # 'call_to_action' from recommendation_type cleanly requires rebuilding
    # the enum type (create new type, migrate column, drop old, rename) -
    # deliberately not automated here since it's a documented Postgres
    # limitation, not an oversight. If a true downgrade is ever needed,
    # do that rebuild by hand at that time.
