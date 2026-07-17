"""M4 AI Outreach Generation Engine: outreach playbooks (+ reusable
blocks), prompt versions, outreach requests/jobs/runs, and the core
versioned/immutable outreach drafts with their edit and evidence trails.
Also adds a forward-looking `scope` column to personalization_snapshots.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-17

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- new enum types -------------------------------------------------------
    personalization_scope = postgresql.ENUM(
        "account", "contact",
        name="personalization_scope", create_type=False,
    )
    outreach_job_status = postgresql.ENUM(
        "pending", "running", "completed", "failed", "cancelled",
        name="outreach_job_status", create_type=False,
    )
    outreach_draft_status = postgresql.ENUM(
        "draft", "pending_approval", "approved", "rejected", "superseded",
        name="outreach_draft_status", create_type=False,
    )
    outreach_block_behavior = postgresql.ENUM(
        "fixed", "ai_assisted", "ai_generated",
        name="outreach_block_behavior", create_type=False,
    )

    for enum_type in (
        personalization_scope, outreach_job_status, outreach_draft_status, outreach_block_behavior,
    ):
        enum_type.create(bind, checkfirst=True)

    # --- personalization_snapshots: add forward-looking scope column --------
    # Existing rows all get 'account' (the only value M3/M4 ever produce);
    # CONTACT is unused until a future per-stakeholder personalization
    # upgrade, added now purely so that upgrade needs no schema change.
    op.add_column(
        "personalization_snapshots",
        sa.Column("scope", personalization_scope, nullable=False, server_default="account"),
    )
    op.create_index("ix_personalization_snapshots_scope", "personalization_snapshots", ["scope"])

    # --- prompt_versions: AI behavior instructions, separate from playbooks -
    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=True),
        sa.Column("channel_key", sa.String(100), nullable=False),
        sa.Column("prompt_key", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_prompt_versions_company_profile_id", "prompt_versions", ["company_profile_id"])
    op.create_index("ix_prompt_versions_channel_key", "prompt_versions", ["channel_key"])
    op.create_index("ix_prompt_versions_prompt_key", "prompt_versions", ["prompt_key"])
    op.create_index("ix_prompt_versions_is_active", "prompt_versions", ["is_active"])

    # --- outreach_playbooks: business knowledge, versioned per (company, name) -
    op.create_table(
        "outreach_playbooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("playbook_goal", sa.String(100), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("derived_from_playbook_version", sa.Integer(), nullable=True),
        sa.Column("is_system_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sales_methodology", sa.Text(), nullable=True),
        sa.Column("brand_voice", sa.Text(), nullable=True),
        sa.Column("core_value_proposition", sa.Text(), nullable=True),
        sa.Column("communication_principles", postgresql.JSONB(), nullable=True),
        sa.Column("personalization_rules", postgresql.JSONB(), nullable=True),
        sa.Column("channel_preferences", postgresql.JSONB(), nullable=True),
        sa.Column("cta_strategy", sa.Text(), nullable=True),
    )
    op.create_index("ix_outreach_playbooks_company_profile_id", "outreach_playbooks", ["company_profile_id"])
    op.create_index("ix_outreach_playbooks_playbook_goal", "outreach_playbooks", ["playbook_goal"])
    op.create_index("ix_outreach_playbooks_is_current", "outreach_playbooks", ["is_current"])

    # --- outreach_blocks: reusable composable pieces of one playbook version -
    op.create_table(
        "outreach_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("outreach_playbook_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outreach_playbooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("block_key", sa.String(100), nullable=False),
        sa.Column("behavior", outreach_block_behavior, nullable=False),
        sa.Column("fixed_content", sa.Text(), nullable=True),
        sa.Column("ai_guidance", sa.Text(), nullable=True),
        sa.Column("applicable_channels", postgresql.JSONB(), nullable=True),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_outreach_blocks_outreach_playbook_id", "outreach_blocks", ["outreach_playbook_id"])
    op.create_index("ix_outreach_blocks_block_key", "outreach_blocks", ["block_key"])

    # --- outreach_requests: per-(prospect_contact, channel) generation intent -
    op.create_table(
        "outreach_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospect_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outreach_playbook_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outreach_playbooks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("channel_key", sa.String(100), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sequence_key", sa.String(255), nullable=True),
        sa.Column("sequence_position", sa.Integer(), nullable=True),
        sa.Column("status", outreach_job_status, nullable=False, server_default="pending"),
    )
    op.create_index("ix_outreach_requests_prospect_id", "outreach_requests", ["prospect_id"])
    op.create_index("ix_outreach_requests_prospect_contact_id", "outreach_requests", ["prospect_contact_id"])
    op.create_index("ix_outreach_requests_company_profile_id", "outreach_requests", ["company_profile_id"])
    op.create_index("ix_outreach_requests_outreach_playbook_id", "outreach_requests", ["outreach_playbook_id"])
    op.create_index("ix_outreach_requests_channel_key", "outreach_requests", ["channel_key"])
    op.create_index("ix_outreach_requests_sequence_key", "outreach_requests", ["sequence_key"])
    op.create_index("ix_outreach_requests_status", "outreach_requests", ["status"])

    # --- outreach_jobs: one synchronous execution ----------------------------
    op.create_table(
        "outreach_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("outreach_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outreach_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospect_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("personalization_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", outreach_job_status, nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("log", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_outreach_jobs_outreach_request_id", "outreach_jobs", ["outreach_request_id"])
    op.create_index("ix_outreach_jobs_prospect_id", "outreach_jobs", ["prospect_id"])
    op.create_index("ix_outreach_jobs_prospect_contact_id", "outreach_jobs", ["prospect_contact_id"])
    op.create_index("ix_outreach_jobs_company_profile_id", "outreach_jobs", ["company_profile_id"])
    op.create_index("ix_outreach_jobs_personalization_snapshot_id", "outreach_jobs", ["personalization_snapshot_id"])
    op.create_index("ix_outreach_jobs_prompt_version_id", "outreach_jobs", ["prompt_version_id"])
    op.create_index("ix_outreach_jobs_status", "outreach_jobs", ["status"])

    # --- outreach_drafts: the core versioned/immutable rendered artifact -----
    op.create_table(
        "outreach_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("outreach_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outreach_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospect_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_key", sa.String(100), nullable=False),
        sa.Column("outreach_playbook_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outreach_playbooks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("outreach_playbook_version", sa.Integer(), nullable=False),
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rendered_prompt", sa.Text(), nullable=True),
        sa.Column("ai_generated_content", postgresql.JSONB(), nullable=False),
        sa.Column("current_content", postgresql.JSONB(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", outreach_draft_status, nullable=False, server_default="draft"),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_outreach_drafts_outreach_job_id", "outreach_drafts", ["outreach_job_id"])
    op.create_index("ix_outreach_drafts_prospect_id", "outreach_drafts", ["prospect_id"])
    op.create_index("ix_outreach_drafts_prospect_contact_id", "outreach_drafts", ["prospect_contact_id"])
    op.create_index("ix_outreach_drafts_company_profile_id", "outreach_drafts", ["company_profile_id"])
    op.create_index("ix_outreach_drafts_channel_key", "outreach_drafts", ["channel_key"])
    op.create_index("ix_outreach_drafts_outreach_playbook_id", "outreach_drafts", ["outreach_playbook_id"])
    op.create_index("ix_outreach_drafts_prompt_version_id", "outreach_drafts", ["prompt_version_id"])
    op.create_index("ix_outreach_drafts_is_current", "outreach_drafts", ["is_current"])
    op.create_index("ix_outreach_drafts_status", "outreach_drafts", ["status"])

    # --- outreach_edits: append-only human-edit audit trail ------------------
    op.create_table(
        "outreach_edits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("outreach_draft_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outreach_drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("edited_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_content", postgresql.JSONB(), nullable=False),
        sa.Column("new_content", postgresql.JSONB(), nullable=False),
        sa.Column("edit_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_outreach_edits_outreach_draft_id", "outreach_edits", ["outreach_draft_id"])

    # --- outreach_evidence: references Strategy/Signal/Recommendation/-------
    # IntelligenceSnapshot only, never duplicates their content, mirrors
    # PersonalizationEvidence/SignalEvidence/RecommendationEvidence.
    op.create_table(
        "outreach_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("outreach_draft_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outreach_drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("block_key", sa.String(100), nullable=True),
        sa.Column("personalization_strategy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_strategies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("signals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("intelligence_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("intelligence_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
    )
    op.create_index("ix_outreach_evidence_outreach_draft_id", "outreach_evidence", ["outreach_draft_id"])
    op.create_index("ix_outreach_evidence_block_key", "outreach_evidence", ["block_key"])
    op.create_index("ix_outreach_evidence_personalization_strategy_id", "outreach_evidence", ["personalization_strategy_id"])
    op.create_index("ix_outreach_evidence_signal_id", "outreach_evidence", ["signal_id"])
    op.create_index("ix_outreach_evidence_recommendation_id", "outreach_evidence", ["recommendation_id"])

    # --- outreach_runs: frozen config snapshot -------------------------------
    op.create_table(
        "outreach_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("outreach_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outreach_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outreach_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outreach_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospect_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("outreach_draft_version_created", sa.Integer(), nullable=True),
        sa.UniqueConstraint("outreach_job_id"),
    )
    op.create_index("ix_outreach_runs_outreach_request_id", "outreach_runs", ["outreach_request_id"])
    op.create_index("ix_outreach_runs_prospect_id", "outreach_runs", ["prospect_id"])
    op.create_index("ix_outreach_runs_prospect_contact_id", "outreach_runs", ["prospect_contact_id"])
    op.create_index("ix_outreach_runs_company_profile_id", "outreach_runs", ["company_profile_id"])

    # --- seed data: one system-default playbook (+ blocks) and prompt version -
    outreach_playbooks_table = sa.table(
        "outreach_playbooks",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("company_profile_id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("playbook_goal", sa.String),
        sa.column("version", sa.Integer),
        sa.column("is_current", sa.Boolean),
        sa.column("derived_from_playbook_version", sa.Integer),
        sa.column("is_system_default", sa.Boolean),
        sa.column("sales_methodology", sa.Text),
        sa.column("brand_voice", sa.Text),
        sa.column("core_value_proposition", sa.Text),
        sa.column("communication_principles", postgresql.JSONB),
        sa.column("personalization_rules", postgresql.JSONB),
        sa.column("channel_preferences", postgresql.JSONB),
        sa.column("cta_strategy", sa.Text),
    )
    playbook_id = uuid.uuid4()
    op.bulk_insert(
        outreach_playbooks_table,
        [
            {
                "id": playbook_id,
                "company_profile_id": None,
                "name": "Standard Export Outreach",
                "description": "Default starter playbook for first-touch B2B export outreach - consultative, evidence-anchored, one clear CTA per message.",
                "playbook_goal": "meeting_request",
                "version": 1,
                "is_current": True,
                "derived_from_playbook_version": None,
                "is_system_default": True,
                "sales_methodology": (
                    "Consultative, evidence-led first contact: open with a specific, "
                    "verified observation about the buyer's business (never generic "
                    "flattery), connect it to a concrete implication, and close with "
                    "exactly one low-friction call-to-action. Never fabricate facts not "
                    "present in Research/Personalization output."
                ),
                "brand_voice": "Professional, direct, confident without overselling.",
                "core_value_proposition": (
                    "Reliable export manufacturing partner with verified certifications "
                    "and consistent on-time delivery."
                ),
                "communication_principles": [
                    "Anchor every message to a real, evidenced signal - never generic outreach.",
                    "One message, one clear call-to-action.",
                    "Keep first-touch messages short - lead with relevance, not backstory.",
                    "Never invent facts not present in the buyer's research/personalization context.",
                ],
                "personalization_rules": {
                    "always_use_current_signal": True,
                    "max_first_touch_word_count": 120,
                },
                "channel_preferences": {
                    "email": {"max_length": 125, "tone": "professional"},
                    "linkedin_message": {"max_length": 400, "tone": "conversational"},
                    "whatsapp": {"max_length": 300, "tone": "casual"},
                },
                "cta_strategy": "Default to a short introductory call or sample request - always exactly one ask per message.",
            }
        ],
    )

    outreach_blocks_table = sa.table(
        "outreach_blocks",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("outreach_playbook_id", postgresql.UUID(as_uuid=True)),
        sa.column("block_key", sa.String),
        sa.column("behavior", outreach_block_behavior),
        sa.column("fixed_content", sa.Text),
        sa.column("ai_guidance", sa.Text),
        sa.column("applicable_channels", postgresql.JSONB),
        sa.column("is_mandatory", sa.Boolean),
        sa.column("display_order", sa.Integer),
    )
    system_blocks = [
        ("greeting", "fixed", "Hello {{buyer}},", None, 0, True),
        ("company_introduction", "ai_assisted", "We are {{company}}, an export manufacturer.", "Lightly personalize the introduction to reference the buyer's industry.", 1, True),
        ("opening_paragraph", "ai_generated", None, "Open with the strongest available signal for this buyer - specific, verified, never generic.", 2, True),
        ("prospect_relevance", "ai_generated", None, "Connect the opening signal to a concrete implication for this buyer's business (SPIN-style: situation -> problem -> implication).", 3, False),
        ("capability_statement", "fixed", "Our facility is certified and equipped for consistent, on-time export production.", None, 4, True),
        ("core_value_proposition", "fixed", "We help buyers like you secure reliable, certified supply without the usual sourcing risk.", None, 5, True),
        ("cta", "ai_generated", None, "Close with exactly one low-friction call-to-action, matching the assigned strategy's CTA slot.", 6, True),
        ("closing_sentence", "ai_generated", None, "Write a brief, warm closing sentence matching the assigned communication strategy's tone.", 7, False),
        ("signature", "fixed", "Best regards,\n{{company}}", None, 8, True),
    ]
    op.bulk_insert(
        outreach_blocks_table,
        [
            {
                "id": uuid.uuid4(),
                "outreach_playbook_id": playbook_id,
                "block_key": block_key,
                "behavior": behavior,
                "fixed_content": fixed_content,
                "ai_guidance": ai_guidance,
                "applicable_channels": None,
                "is_mandatory": is_mandatory,
                "display_order": display_order,
            }
            for block_key, behavior, fixed_content, ai_guidance, display_order, is_mandatory in system_blocks
        ],
    )

    prompt_versions_table = sa.table(
        "prompt_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("company_profile_id", postgresql.UUID(as_uuid=True)),
        sa.column("channel_key", sa.String),
        sa.column("prompt_key", sa.String),
        sa.column("version", sa.Integer),
        sa.column("prompt_text", sa.Text),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        prompt_versions_table,
        [
            {
                "id": uuid.uuid4(),
                "company_profile_id": None,
                "channel_key": "email",
                "prompt_key": "email_generation",
                "version": 1,
                "prompt_text": (
                    "You are generating one block of a B2B export outreach email. "
                    "Use only the verified facts provided in the personalization "
                    "variables and playbook block guidance - never invent facts, "
                    "statistics, or claims not present in the supplied context. "
                    "Respect the playbook's brand voice, core value proposition, and "
                    "communication principles exactly. Follow the assigned "
                    "communication strategy (formality, directness, warmth, "
                    "technical depth, authority, consultative level, urgency, "
                    "message length) precisely. Generate structured output for "
                    "exactly the block requested - do not write the whole message at "
                    "once. Anchor every generated block to a specific signal, "
                    "recommendation, or strategy provided - never generic filler."
                ),
                "is_active": True,
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("outreach_runs")
    op.drop_table("outreach_evidence")
    op.drop_table("outreach_edits")
    op.drop_table("outreach_drafts")
    op.drop_table("outreach_jobs")
    op.drop_table("outreach_requests")
    op.drop_table("outreach_blocks")
    op.drop_table("outreach_playbooks")
    op.drop_table("prompt_versions")

    op.drop_index("ix_personalization_snapshots_scope", table_name="personalization_snapshots")
    op.drop_column("personalization_snapshots", "scope")

    bind = op.get_bind()
    postgresql.ENUM(name="outreach_block_behavior", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="outreach_draft_status", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="outreach_job_status", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="personalization_scope", create_type=False).drop(bind, checkfirst=True)
