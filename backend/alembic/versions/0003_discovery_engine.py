"""M1 Buyer Discovery Engine: search templates, searches, jobs, provider
runs, raw provider results, discovery runs, prospects, prospect contacts,
prospect sources, prospect timeline events.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-15

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- new enum types (same create_type=False + explicit create()
    # pattern established in 0001/0002) -------------------------------------
    discovery_job_status = postgresql.ENUM(
        "pending", "running", "completed", "partially_completed", "failed", "cancelled",
        name="discovery_job_status", create_type=False,
    )
    prospect_status = postgresql.ENUM(
        "new", "duplicate_review", "scored", "qualified", "unqualified",
        "in_review", "approved", "rejected", "archived",
        name="prospect_status", create_type=False,
    )
    decision_maker_level = postgresql.ENUM(
        "final_decision_maker", "influencer", "gatekeeper", "unknown",
        name="decision_maker_level", create_type=False,
    )
    for enum_type in (discovery_job_status, prospect_status, decision_maker_level):
        enum_type.create(bind, checkfirst=True)

    # --- search_templates: company_profile_id nullable so a small set of
    # system-seeded starter templates can exist without belonging to any
    # one business. ---------------------------------------------------------
    op.create_table(
        "search_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("query_spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_system_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_search_templates_company_profile_id", "search_templates", ["company_profile_id"])

    # --- discovery_searches: Search Template -> Search -> Job. Template is
    # a hard requirement (NOT NULL, ondelete=RESTRICT - a template in use
    # can't be silently deleted out from under a search). No relationship
    # to Product: products are read directly off the CompanyProfile via the
    # bound ICP at run time instead of a second configuration surface here. -
    op.create_table(
        "discovery_searches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("search_template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("search_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("icp_criteria_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("icp_criteria.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("query_spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("provider_keys", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("search_depth", postgresql.ENUM("quick", "standard", "deep", name="search_depth", create_type=False), nullable=False, server_default="standard"),
        sa.Column("search_frequency", postgresql.ENUM("manual", "daily", "weekly", name="search_frequency", create_type=False), nullable=False, server_default="manual"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_discovery_searches_company_profile_id", "discovery_searches", ["company_profile_id"])
    op.create_index("ix_discovery_searches_search_template_id", "discovery_searches", ["search_template_id"])
    op.create_index("ix_discovery_searches_icp_criteria_id", "discovery_searches", ["icp_criteria_id"])

    # --- discovery_jobs: one execution of a DiscoverySearch. Synchronous
    # only in M1 (no worker/queue), but the status enum already models
    # pending/running/cancelled for a future async executor. ---------------
    op.create_table(
        "discovery_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("discovery_search_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("discovery_searches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", discovery_job_status, nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("providers_used", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("raw_result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prospect_created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prospect_matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("log", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_discovery_jobs_discovery_search_id", "discovery_jobs", ["discovery_search_id"])
    op.create_index("ix_discovery_jobs_company_profile_id", "discovery_jobs", ["company_profile_id"])
    op.create_index("ix_discovery_jobs_status", "discovery_jobs", ["status"])

    # --- discovery_job_provider_runs: per-provider execution metrics
    # (duration, cost, tokens, requests) within one job. --------------------
    op.create_table(
        "discovery_job_provider_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("discovery_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("discovery_jobs.id", ondelete="CASCADE"), nullable=False),
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
    op.create_index("ix_discovery_job_provider_runs_discovery_job_id", "discovery_job_provider_runs", ["discovery_job_id"])
    op.create_index("ix_discovery_job_provider_runs_provider_key", "discovery_job_provider_runs", ["provider_key"])

    # --- prospects: the durable, deduplicated, scored candidate. Entirely
    # separate from the CRM's companies table by design. Self-referencing
    # FK for potential_duplicate_of_prospect_id is valid within one
    # CREATE TABLE in Postgres. ----------------------------------------------
    op.create_table(
        "prospects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("discovery_search_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("discovery_searches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("industry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("industries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("industry_raw", sa.String(255), nullable=True),
        sa.Column("buyer_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buyer_types.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_size_range", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", prospect_status, nullable=False, server_default="new"),
        sa.Column("total_score", sa.Float(), nullable=True),
        sa.Column("score_breakdown", postgresql.JSONB(), nullable=True),
        sa.Column("ai_reasoning", sa.Text(), nullable=True),
        sa.Column("first_discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("potential_duplicate_of_prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("duplicate_confidence", sa.Float(), nullable=True),
        sa.Column("timezone", sa.String(100), nullable=True),
    )
    op.create_index("ix_prospects_company_profile_id", "prospects", ["company_profile_id"])
    op.create_index("ix_prospects_discovery_search_id", "prospects", ["discovery_search_id"])
    op.create_index("ix_prospects_status", "prospects", ["status"])

    # --- discovery_provider_results: append-only raw payload staging,
    # preserved permanently for future AI enrichment. ------------------------
    op.create_table(
        "discovery_provider_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("discovery_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("discovery_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_key", sa.String(100), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("normalized_payload", postgresql.JSONB(), nullable=True),
        sa.Column("dedup_key", sa.String(500), nullable=True),
        sa.Column("matched_prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_discovery_provider_results_discovery_job_id", "discovery_provider_results", ["discovery_job_id"])
    op.create_index("ix_discovery_provider_results_provider_key", "discovery_provider_results", ["provider_key"])
    op.create_index("ix_discovery_provider_results_dedup_key", "discovery_provider_results", ["dedup_key"])
    op.create_index("ix_discovery_provider_results_matched_prospect_id", "discovery_provider_results", ["matched_prospect_id"])

    # --- prospect_contacts: mirrors Contact's field set closely, plus
    # discovery-specific department/decision_maker_level. --------------------
    op.create_table(
        "prospect_contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(255), nullable=True),
        sa.Column("department", sa.String(255), nullable=True),
        sa.Column("decision_maker_level", decision_maker_level, nullable=False, server_default="unknown"),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("timezone", sa.String(100), nullable=True),
        sa.Column("working_hours", postgresql.JSONB(), nullable=True),
        sa.Column("preferred_contact_time", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_prospect_contacts_prospect_id", "prospect_contacts", ["prospect_id"])
    op.create_index("ix_prospect_contacts_email", "prospect_contacts", ["email"])

    # --- prospect_sources: every provider occurrence preserved
    # individually, with its own timestamp/URL/provider_confidence, instead
    # of a flat source_provider_keys list. -----------------------------------
    op.create_table(
        "prospect_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_key", sa.String(100), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_confidence", sa.Float(), nullable=True),
        sa.Column("raw_result_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("discovery_provider_results.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_prospect_sources_prospect_id", "prospect_sources", ["prospect_id"])
    op.create_index("ix_prospect_sources_provider_key", "prospect_sources", ["provider_key"])

    # --- prospect_timeline_events: open event_type + JSONB payload so a
    # future AI agent can append new kinds of events without a migration. ---
    op.create_table(
        "prospect_timeline_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False, server_default="system"),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_prospect_timeline_events_prospect_id", "prospect_timeline_events", ["prospect_id"])
    op.create_index("ix_prospect_timeline_events_event_type", "prospect_timeline_events", ["event_type"])

    # --- discovery_runs (formerly considered "Search History"): frozen
    # config snapshot + result counts for one execution, 1:1 with the job. --
    op.create_table(
        "discovery_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("discovery_search_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("discovery_searches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("discovery_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("discovery_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("prospects_found_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_prospects_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("discovery_job_id"),
    )
    op.create_index("ix_discovery_runs_discovery_search_id", "discovery_runs", ["discovery_search_id"])
    op.create_index("ix_discovery_runs_company_profile_id", "discovery_runs", ["company_profile_id"])

    # --- seed data: a handful of system starter templates, cloned per
    # business the same way reference data is "seeded, then customized". ----
    search_templates_table = sa.table(
        "search_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("company_profile_id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("query_spec", postgresql.JSONB),
        sa.column("is_system_default", sa.Boolean),
    )
    system_templates = [
        (
            "General Buyer Search",
            "Broad search across all enabled providers, using this business's active ICP and products.",
            {"keywords": [], "regions": []},
        ),
        (
            "Importers - Broad",
            "Targets import-focused buyers matching the active ICP's target markets.",
            {"buyer_type_hint": "Importers", "regions": []},
        ),
        (
            "Trade Show / Distributor Search",
            "Targets distributors and buying offices typically sourced via trade shows.",
            {"buyer_type_hint": "Distributors", "channel_hint": "trade_show"},
        ),
    ]
    op.bulk_insert(
        search_templates_table,
        [
            {
                "id": uuid.uuid4(),
                "company_profile_id": None,
                "name": name,
                "description": description,
                "query_spec": query_spec,
                "is_system_default": True,
            }
            for name, description, query_spec in system_templates
        ],
    )


def downgrade() -> None:
    op.drop_table("discovery_runs")
    op.drop_table("prospect_timeline_events")
    op.drop_table("prospect_sources")
    op.drop_table("prospect_contacts")
    op.drop_table("discovery_provider_results")
    op.drop_table("prospects")
    op.drop_table("discovery_job_provider_runs")
    op.drop_table("discovery_jobs")
    op.drop_table("discovery_searches")
    op.drop_table("search_templates")

    bind = op.get_bind()
    postgresql.ENUM(name="decision_maker_level", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="prospect_status", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="discovery_job_status", create_type=False).drop(bind, checkfirst=True)
