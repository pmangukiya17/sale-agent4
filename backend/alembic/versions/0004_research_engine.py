"""M2 AI Research & Prospect Intelligence: research templates, requests,
jobs, provider runs, sources, raw documents, AI analyses, intelligence
snapshots, signals, recommendations, research reports, research runs.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-15

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- new enum types (same create_type=False + explicit create()
    # pattern established in 0001/0002/0003) --------------------------------
    research_job_status = postgresql.ENUM(
        "pending", "running", "completed", "partially_completed", "failed", "cancelled",
        name="research_job_status", create_type=False,
    )
    ai_analysis_type = postgresql.ENUM(
        "company_profile", "buyer_profile", "business_signals", "sales_intelligence",
        name="ai_analysis_type", create_type=False,
    )
    signal_status = postgresql.ENUM("new", "reviewed", "dismissed", name="signal_status", create_type=False)
    signal_importance = postgresql.ENUM("low", "medium", "high", "critical", name="signal_importance", create_type=False)
    signal_urgency = postgresql.ENUM("low", "medium", "high", "immediate", name="signal_urgency", create_type=False)
    recommendation_type = postgresql.ENUM(
        "product_fit", "sales_angle", "talking_point", "objection_handling", "risk_mitigation",
        name="recommendation_type", create_type=False,
    )
    recommendation_status = postgresql.ENUM("new", "accepted", "dismissed", name="recommendation_status", create_type=False)

    for enum_type in (
        research_job_status, ai_analysis_type, signal_status, signal_importance,
        signal_urgency, recommendation_type, recommendation_status,
    ):
        enum_type.create(bind, checkfirst=True)

    # --- research_templates: mirrors search_templates (0003) exactly ------
    op.create_table(
        "research_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("research_spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_system_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_research_templates_company_profile_id", "research_templates", ["company_profile_id"])

    # --- research_requests: Template -> Request -> Job, mandatory template -
    op.create_table(
        "research_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("research_template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_focus_areas", postgresql.JSONB(), nullable=True),
        sa.Column("status", research_job_status, nullable=False, server_default="pending"),
    )
    op.create_index("ix_research_requests_prospect_id", "research_requests", ["prospect_id"])
    op.create_index("ix_research_requests_company_profile_id", "research_requests", ["company_profile_id"])
    op.create_index("ix_research_requests_research_template_id", "research_requests", ["research_template_id"])
    op.create_index("ix_research_requests_status", "research_requests", ["status"])

    # --- research_jobs: one synchronous execution --------------------------
    op.create_table(
        "research_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("research_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", research_job_status, nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sources_used", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("raw_document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("log", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_research_jobs_research_request_id", "research_jobs", ["research_request_id"])
    op.create_index("ix_research_jobs_prospect_id", "research_jobs", ["prospect_id"])
    op.create_index("ix_research_jobs_company_profile_id", "research_jobs", ["company_profile_id"])
    op.create_index("ix_research_jobs_status", "research_jobs", ["status"])

    # --- research_job_provider_runs: per-provider execution metrics --------
    op.create_table(
        "research_job_provider_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("research_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_key", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("api_cost", sa.Numeric(10, 4), nullable=True),
        sa.Column("token_usage", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="completed"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_research_job_provider_runs_research_job_id", "research_job_provider_runs", ["research_job_id"])
    op.create_index("ix_research_job_provider_runs_provider_key", "research_job_provider_runs", ["provider_key"])

    # --- research_sources: one attempted fetch from one provider -----------
    op.create_table(
        "research_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("research_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_key", sa.String(100), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("source_identifier", sa.String(500), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_research_sources_research_job_id", "research_sources", ["research_job_id"])
    op.create_index("ix_research_sources_provider_key", "research_sources", ["provider_key"])

    # --- raw_documents: permanent, never-discarded evidence -----------------
    op.create_table(
        "raw_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("research_source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("raw_html", sa.Text(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("doc_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_raw_documents_research_source_id", "raw_documents", ["research_source_id"])
    op.create_index("ix_raw_documents_prospect_id", "raw_documents", ["prospect_id"])
    op.create_index("ix_raw_documents_content_hash", "raw_documents", ["content_hash"])

    # --- ai_analyses: one analysis pass, typed by analysis_type -------------
    op.create_table(
        "ai_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("research_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_type", ai_analysis_type, nullable=False),
        sa.Column("model_used", sa.String(255), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("raw_model_output", postgresql.JSONB(), nullable=True),
        sa.Column("structured_output", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("token_usage", sa.Integer(), nullable=True),
        sa.Column("api_cost", sa.Numeric(10, 4), nullable=True),
    )
    op.create_index("ix_ai_analyses_research_job_id", "ai_analyses", ["research_job_id"])
    op.create_index("ix_ai_analyses_prospect_id", "ai_analyses", ["prospect_id"])
    op.create_index("ix_ai_analyses_analysis_type", "ai_analyses", ["analysis_type"])

    # --- ai_analysis_source_documents: evidence trail junction -------------
    op.create_table(
        "ai_analysis_source_documents",
        sa.Column("ai_analysis_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_analyses.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("raw_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("raw_documents.id", ondelete="CASCADE"), primary_key=True),
    )

    # --- intelligence_snapshots: versioned, never overwritten ---------------
    op.create_table(
        "intelligence_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("research_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("business_model", sa.String(255), nullable=True),
        sa.Column("products_offered", postgresql.JSONB(), nullable=True),
        sa.Column("markets_served", postgresql.JSONB(), nullable=True),
        sa.Column("certifications", postgresql.JSONB(), nullable=True),
        sa.Column("manufacturing_or_trading", sa.String(255), nullable=True),
        sa.Column("sustainability_notes", sa.Text(), nullable=True),
        sa.Column("import_export_activity", postgresql.JSONB(), nullable=True),
        sa.Column("buyer_notes", sa.Text(), nullable=True),
        sa.Column("procurement_structure", sa.Text(), nullable=True),
        sa.Column("purchasing_process", sa.Text(), nullable=True),
        sa.Column("signals_summary", sa.Text(), nullable=True),
    )
    op.create_index("ix_intelligence_snapshots_prospect_id", "intelligence_snapshots", ["prospect_id"])
    op.create_index("ix_intelligence_snapshots_research_job_id", "intelligence_snapshots", ["research_job_id"])
    op.create_index("ix_intelligence_snapshots_company_profile_id", "intelligence_snapshots", ["company_profile_id"])
    op.create_index("ix_intelligence_snapshots_is_current", "intelligence_snapshots", ["is_current"])

    # --- signals: atomic, evidenced, importance/urgency extend M2 round 2 --
    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("intelligence_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("intelligence_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("signal_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("importance", signal_importance, nullable=False, server_default="medium"),
        sa.Column("urgency", signal_urgency, nullable=False, server_default="medium"),
        sa.Column("status", signal_status, nullable=False, server_default="new"),
    )
    op.create_index("ix_signals_prospect_id", "signals", ["prospect_id"])
    op.create_index("ix_signals_intelligence_snapshot_id", "signals", ["intelligence_snapshot_id"])
    op.create_index("ix_signals_signal_type", "signals", ["signal_type"])
    op.create_index("ix_signals_importance", "signals", ["importance"])
    op.create_index("ix_signals_urgency", "signals", ["urgency"])
    op.create_index("ix_signals_status", "signals", ["status"])

    op.create_table(
        "signal_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("signals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("raw_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ai_analysis_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_analyses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
    )
    op.create_index("ix_signal_evidence_signal_id", "signal_evidence", ["signal_id"])
    op.create_index("ix_signal_evidence_raw_document_id", "signal_evidence", ["raw_document_id"])

    # --- recommendations: prescriptive, classified by recommendation_type --
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("intelligence_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("intelligence_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recommendation_type", recommendation_type, nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("status", recommendation_status, nullable=False, server_default="new"),
    )
    op.create_index("ix_recommendations_prospect_id", "recommendations", ["prospect_id"])
    op.create_index("ix_recommendations_intelligence_snapshot_id", "recommendations", ["intelligence_snapshot_id"])
    op.create_index("ix_recommendations_recommendation_type", "recommendations", ["recommendation_type"])
    op.create_index("ix_recommendations_status", "recommendations", ["status"])

    op.create_table(
        "recommendation_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("raw_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ai_analysis_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_analyses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
    )
    op.create_index("ix_recommendation_evidence_recommendation_id", "recommendation_evidence", ["recommendation_id"])
    op.create_index("ix_recommendation_evidence_raw_document_id", "recommendation_evidence", ["raw_document_id"])

    # --- research_reports: generated FROM a snapshot, never independent ----
    op.create_table(
        "research_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("intelligence_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("intelligence_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("research_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_by", sa.String(255), nullable=False, server_default="system"),
    )
    op.create_index("ix_research_reports_prospect_id", "research_reports", ["prospect_id"])
    op.create_index("ix_research_reports_intelligence_snapshot_id", "research_reports", ["intelligence_snapshot_id"])

    # --- research_runs: frozen config snapshot, mirrors discovery_runs -----
    op.create_table(
        "research_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("research_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("research_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("documents_found_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("intelligence_version_created", sa.Integer(), nullable=True),
        sa.UniqueConstraint("research_job_id"),
    )
    op.create_index("ix_research_runs_research_request_id", "research_runs", ["research_request_id"])
    op.create_index("ix_research_runs_prospect_id", "research_runs", ["prospect_id"])
    op.create_index("ix_research_runs_company_profile_id", "research_runs", ["company_profile_id"])

    # --- seed data: system starter templates --------------------------------
    research_templates_table = sa.table(
        "research_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("company_profile_id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("research_spec", postgresql.JSONB),
        sa.column("is_system_default", sa.Boolean),
    )
    system_templates = [
        (
            "Standard Company Research",
            "Company website + news, covering business model, products, markets, and certifications.",
            {"source_types": ["manual_document"], "depth": "standard", "focus_areas": ["company_profile", "business_signals"]},
        ),
        (
            "Deep Buyer & Signals Research",
            "Broader pass covering decision makers, procurement structure, and business signals.",
            {"source_types": ["manual_document"], "depth": "deep", "focus_areas": ["buyer_profile", "business_signals", "sales_intelligence"]},
        ),
        (
            "Quick Website Scan",
            "Fast, shallow pass over whatever documents are supplied - a starting point, not exhaustive.",
            {"source_types": ["manual_document"], "depth": "quick", "focus_areas": ["company_profile"]},
        ),
    ]
    op.bulk_insert(
        research_templates_table,
        [
            {
                "id": uuid.uuid4(),
                "company_profile_id": None,
                "name": name,
                "description": description,
                "research_spec": research_spec,
                "is_system_default": True,
            }
            for name, description, research_spec in system_templates
        ],
    )


def downgrade() -> None:
    op.drop_table("research_runs")
    op.drop_table("research_reports")
    op.drop_table("recommendation_evidence")
    op.drop_table("recommendations")
    op.drop_table("signal_evidence")
    op.drop_table("signals")
    op.drop_table("intelligence_snapshots")
    op.drop_table("ai_analysis_source_documents")
    op.drop_table("ai_analyses")
    op.drop_table("raw_documents")
    op.drop_table("research_sources")
    op.drop_table("research_job_provider_runs")
    op.drop_table("research_jobs")
    op.drop_table("research_requests")
    op.drop_table("research_templates")

    bind = op.get_bind()
    postgresql.ENUM(name="recommendation_status", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="recommendation_type", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="signal_urgency", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="signal_importance", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="signal_status", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="ai_analysis_type", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="research_job_status", create_type=False).drop(bind, checkfirst=True)
