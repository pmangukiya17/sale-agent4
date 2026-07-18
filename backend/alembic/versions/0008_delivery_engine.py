"""M5 Outreach Delivery Engine (Layer 2): sending_profiles,
provider_connections (+ provider_credentials, split out as its own table so
credential storage can move from Postgres+Fernet to Vault/Key Vault/Secrets
Manager later without touching provider_connections), delivery_campaigns,
delivery_queue_items, and the append-only delivery_events log. Also adds
default_timezone/timezone_note to countries (M0 reference table) so the
Delivery timezone resolver has a real fallback - Prospect/ProspectContact.
timezone are almost always null in practice today.

Delivery does not reuse M1-M4's Template->Request->Job->Run shape - see
delivery_campaign.py's docstring - so this migration's tables have no
direct counterpart pattern from 0002-0007 beyond the general conventions
(UUID PKs, TimestampMixin columns, values_callable enums, RESTRICT on
FKs that must never silently vanish out from under a referencing row).

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- new enum types ---------------------------------------------------
    provider_connection_status = postgresql.ENUM(
        "connected", "expired", "revoked", "error", "disconnected",
        name="provider_connection_status", create_type=False,
    )
    delivery_campaign_status = postgresql.ENUM(
        "draft", "active", "paused", "completed", "cancelled",
        name="delivery_campaign_status", create_type=False,
    )
    delivery_queue_item_status = postgresql.ENUM(
        "queued", "scheduled", "sending", "sent", "failed", "cancelled", "retry",
        name="delivery_queue_item_status", create_type=False,
    )
    delivery_event_type = postgresql.ENUM(
        "queued", "scheduled", "started", "sent", "retry", "failed", "cancelled",
        name="delivery_event_type", create_type=False,
    )

    for enum_type in (
        provider_connection_status, delivery_campaign_status, delivery_queue_item_status, delivery_event_type,
    ):
        enum_type.create(bind, checkfirst=True)

    # --- countries: timezone-inference fallback (M0 reference table) ------
    op.add_column("countries", sa.Column("default_timezone", sa.String(100), nullable=True))
    op.add_column("countries", sa.Column("timezone_note", sa.String(255), nullable=True))

    countries_table = sa.table(
        "countries", sa.column("code", sa.String), sa.column("default_timezone", sa.String)
    )
    # Every country seeded by 0002 is effectively single-timezone - none of
    # the classic multi-zone cases (US/RU/AU/BR/CA) exist in the seed data
    # yet, so timezone_note stays null for all of these. The column exists
    # for when a multi-zone country is added later, not because one needs
    # it today.
    country_timezones = {
        "DE": "Europe/Berlin", "FR": "Europe/Paris", "IT": "Europe/Rome", "ES": "Europe/Madrid",
        "GB": "Europe/London", "NL": "Europe/Amsterdam", "BE": "Europe/Brussels", "PL": "Europe/Warsaw",
        "PT": "Europe/Lisbon", "SE": "Europe/Stockholm", "AT": "Europe/Vienna", "CH": "Europe/Zurich",
        "IE": "Europe/Dublin", "DK": "Europe/Copenhagen", "NO": "Europe/Oslo", "FI": "Europe/Helsinki",
        "GR": "Europe/Athens", "CZ": "Europe/Prague", "RO": "Europe/Bucharest", "HU": "Europe/Budapest",
        "AE": "Asia/Dubai", "SA": "Asia/Riyadh", "QA": "Asia/Qatar", "KW": "Asia/Kuwait",
        "BH": "Asia/Bahrain", "OM": "Asia/Muscat", "IL": "Asia/Jerusalem", "JO": "Asia/Amman",
        "LB": "Asia/Beirut", "TR": "Europe/Istanbul",
        "EG": "Africa/Cairo", "MA": "Africa/Casablanca", "TN": "Africa/Tunis", "DZ": "Africa/Algiers",
        "LY": "Africa/Tripoli",
    }
    for code, tz in country_timezones.items():
        op.execute(
            countries_table.update().where(countries_table.c.code == code).values(default_timezone=tz)
        )

    # --- provider_connections: one OAuth grant to one real mailbox --------
    op.create_table(
        "provider_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_key", sa.String(100), nullable=False),
        sa.Column("external_account_email", sa.String(255), nullable=True),
        sa.Column("scopes_granted", postgresql.JSONB(), nullable=True),
        sa.Column("status", provider_connection_status, nullable=False, server_default="connected"),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verification_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verification_detail", sa.Text(), nullable=True),
    )
    op.create_index("ix_provider_connections_company_profile_id", "provider_connections", ["company_profile_id"])
    op.create_index("ix_provider_connections_provider_key", "provider_connections", ["provider_key"])
    op.create_index("ix_provider_connections_status", "provider_connections", ["status"])

    # --- provider_credentials: the credential-storage abstraction ---------
    op.create_table(
        "provider_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("provider_connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("provider_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("backend", sa.String(100), nullable=False),
        sa.Column("secret_ref", sa.String(1000), nullable=True),
        sa.Column("encrypted_payload", sa.Text(), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider_connection_id", name="uq_provider_credentials_provider_connection_id"),
    )
    op.create_index("ix_provider_credentials_provider_connection_id", "provider_credentials", ["provider_connection_id"])
    op.create_index("ix_provider_credentials_backend", "provider_credentials", ["backend"])

    # --- sending_profiles: named sending identities ("CEO"/"Sales"/...) ---
    op.create_table(
        "sending_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("provider_connections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider_key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("sender_name", sa.String(255), nullable=False),
        sa.Column("sender_email", sa.String(255), nullable=False),
        sa.Column("reply_to_email", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("daily_limit", sa.Integer(), nullable=True),
        sa.Column("hourly_limit", sa.Integer(), nullable=True),
        sa.Column("min_gap_seconds", sa.Integer(), nullable=True),
        sa.Column("max_gap_seconds", sa.Integer(), nullable=True),
        sa.Column("sending_window_start", sa.Time(), nullable=True),
        sa.Column("sending_window_end", sa.Time(), nullable=True),
        sa.Column("sending_timezone", sa.String(100), nullable=True),
        sa.Column("sending_days", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_sending_profiles_company_profile_id", "sending_profiles", ["company_profile_id"])
    op.create_index("ix_sending_profiles_provider_connection_id", "sending_profiles", ["provider_connection_id"])
    op.create_index("ix_sending_profiles_provider_key", "sending_profiles", ["provider_key"])

    # --- delivery_campaigns: "send these N approved drafts through this
    # sending profile" - see delivery_campaign.py docstring for why this is
    # NOT a Request/Job/Run table. ------------------------------------------
    op.create_table(
        "delivery_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sending_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sending_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", delivery_campaign_status, nullable=False, server_default="draft"),
        sa.Column("sending_window_start", sa.Time(), nullable=True),
        sa.Column("sending_window_end", sa.Time(), nullable=True),
        sa.Column("min_gap_seconds", sa.Integer(), nullable=True),
        sa.Column("max_gap_seconds", sa.Integer(), nullable=True),
        sa.Column("hourly_limit", sa.Integer(), nullable=True),
        sa.Column("daily_limit", sa.Integer(), nullable=True),
        sa.Column("respect_recipient_timezone", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_delivery_campaigns_company_profile_id", "delivery_campaigns", ["company_profile_id"])
    op.create_index("ix_delivery_campaigns_sending_profile_id", "delivery_campaigns", ["sending_profile_id"])
    op.create_index("ix_delivery_campaigns_status", "delivery_campaigns", ["status"])

    # --- delivery_queue_items: one row per approved draft, frozen at
    # enqueue time (see delivery_queue_item.py docstring). -----------------
    op.create_table(
        "delivery_queue_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("delivery_campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("delivery_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outreach_draft_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outreach_drafts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospect_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sending_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sending_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("channel_key", sa.String(100), nullable=False),
        sa.Column("frozen_content", postgresql.JSONB(), nullable=False),
        sa.Column("frozen_draft_version", sa.Integer(), nullable=False),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("recipient_timezone", sa.String(100), nullable=True),
        sa.Column("status", delivery_queue_item_status, nullable=False, server_default="queued"),
        sa.Column("scheduled_send_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("provider_message_id", sa.String(500), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_delivery_queue_items_delivery_campaign_id", "delivery_queue_items", ["delivery_campaign_id"])
    op.create_index("ix_delivery_queue_items_outreach_draft_id", "delivery_queue_items", ["outreach_draft_id"])
    op.create_index("ix_delivery_queue_items_prospect_id", "delivery_queue_items", ["prospect_id"])
    op.create_index("ix_delivery_queue_items_prospect_contact_id", "delivery_queue_items", ["prospect_contact_id"])
    op.create_index("ix_delivery_queue_items_company_profile_id", "delivery_queue_items", ["company_profile_id"])
    op.create_index("ix_delivery_queue_items_sending_profile_id", "delivery_queue_items", ["sending_profile_id"])
    op.create_index("ix_delivery_queue_items_channel_key", "delivery_queue_items", ["channel_key"])
    op.create_index("ix_delivery_queue_items_status", "delivery_queue_items", ["status"])
    op.create_index("ix_delivery_queue_items_scheduled_send_at", "delivery_queue_items", ["scheduled_send_at"])
    # Duplicate-delivery prevention: the same draft can only be queued once
    # while a prior queue item for it is still active - partial unique index
    # rather than a plain UniqueConstraint so a draft CAN be re-queued after
    # its previous queue item reached a terminal state (sent/failed/cancelled).
    op.create_index(
        "uq_delivery_queue_items_active_draft",
        "delivery_queue_items",
        ["outreach_draft_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'scheduled', 'sending', 'retry')"),
    )

    # --- delivery_events: append-only per-queue-item history ---------------
    op.create_table(
        "delivery_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("delivery_queue_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("delivery_queue_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", delivery_event_type, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_delivery_events_delivery_queue_item_id", "delivery_events", ["delivery_queue_item_id"])
    op.create_index("ix_delivery_events_event_type", "delivery_events", ["event_type"])
    op.create_index("ix_delivery_events_occurred_at", "delivery_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_delivery_events_occurred_at", table_name="delivery_events")
    op.drop_index("ix_delivery_events_event_type", table_name="delivery_events")
    op.drop_index("ix_delivery_events_delivery_queue_item_id", table_name="delivery_events")
    op.drop_table("delivery_events")

    op.drop_index("uq_delivery_queue_items_active_draft", table_name="delivery_queue_items")
    op.drop_index("ix_delivery_queue_items_scheduled_send_at", table_name="delivery_queue_items")
    op.drop_index("ix_delivery_queue_items_status", table_name="delivery_queue_items")
    op.drop_index("ix_delivery_queue_items_channel_key", table_name="delivery_queue_items")
    op.drop_index("ix_delivery_queue_items_sending_profile_id", table_name="delivery_queue_items")
    op.drop_index("ix_delivery_queue_items_company_profile_id", table_name="delivery_queue_items")
    op.drop_index("ix_delivery_queue_items_prospect_contact_id", table_name="delivery_queue_items")
    op.drop_index("ix_delivery_queue_items_prospect_id", table_name="delivery_queue_items")
    op.drop_index("ix_delivery_queue_items_outreach_draft_id", table_name="delivery_queue_items")
    op.drop_index("ix_delivery_queue_items_delivery_campaign_id", table_name="delivery_queue_items")
    op.drop_table("delivery_queue_items")

    op.drop_index("ix_delivery_campaigns_status", table_name="delivery_campaigns")
    op.drop_index("ix_delivery_campaigns_sending_profile_id", table_name="delivery_campaigns")
    op.drop_index("ix_delivery_campaigns_company_profile_id", table_name="delivery_campaigns")
    op.drop_table("delivery_campaigns")

    op.drop_index("ix_sending_profiles_provider_key", table_name="sending_profiles")
    op.drop_index("ix_sending_profiles_provider_connection_id", table_name="sending_profiles")
    op.drop_index("ix_sending_profiles_company_profile_id", table_name="sending_profiles")
    op.drop_table("sending_profiles")

    op.drop_index("ix_provider_credentials_backend", table_name="provider_credentials")
    op.drop_index("ix_provider_credentials_provider_connection_id", table_name="provider_credentials")
    op.drop_table("provider_credentials")

    op.drop_index("ix_provider_connections_status", table_name="provider_connections")
    op.drop_index("ix_provider_connections_provider_key", table_name="provider_connections")
    op.drop_index("ix_provider_connections_company_profile_id", table_name="provider_connections")
    op.drop_table("provider_connections")

    op.drop_column("countries", "timezone_note")
    op.drop_column("countries", "default_timezone")

    bind = op.get_bind()
    postgresql.ENUM(name="delivery_event_type", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="delivery_queue_item_status", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="delivery_campaign_status", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="provider_connection_status", create_type=False).drop(bind, checkfirst=True)
