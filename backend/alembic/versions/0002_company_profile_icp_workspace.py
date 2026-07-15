"""company profiles, products, ICP expansion, knowledge base, workspace settings

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-15

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- new enum types (same create_type=False + explicit create()
    # pattern established in 0001, for the same reason: op.create_table's
    # automatic before_create hook would otherwise re-issue CREATE TYPE and
    # collide with the explicit .create() call below). -------------------
    product_status = postgresql.ENUM("active", "inactive", name="product_status", create_type=False)
    search_depth = postgresql.ENUM("quick", "standard", "deep", name="search_depth", create_type=False)
    search_frequency = postgresql.ENUM("manual", "daily", "weekly", name="search_frequency", create_type=False)
    date_format = postgresql.ENUM("DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD", name="date_format", create_type=False)
    time_format = postgresql.ENUM("12h", "24h", name="time_format", create_type=False)

    for enum_type in (product_status, search_depth, search_frequency, date_format, time_format):
        enum_type.create(bind, checkfirst=True)

    # --- reference tables (seeded below; adding a new option later is a
    # data change, not a code deploy) -------------------------------------
    op.create_table(
        "buyer_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "industries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "countries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(4), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_countries_region", "countries", ["region"])

    op.create_table(
        "languages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(8), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "currencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(8), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("symbol", sa.String(8), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("code"),
    )

    # --- company_profiles: NOT a singleton - owner_user_id is a plain
    # (non-unique) FK so one user can own multiple businesses. -----------
    op.create_table(
        "company_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("address", sa.String(1000), nullable=True),
        sa.Column("about", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("business_type", postgresql.JSONB(), nullable=True),
        sa.Column("production_capacity", sa.String(500), nullable=True),
        sa.Column("factory_location", sa.String(500), nullable=True),
        sa.Column("shipping_ports", postgresql.JSONB(), nullable=True),
        sa.Column("export_certifications", postgresql.JSONB(), nullable=True),
        sa.Column("minimum_order_quantity", sa.String(255), nullable=True),
        sa.Column("preferred_incoterms", postgresql.JSONB(), nullable=True),
        sa.Column("preferred_payment_terms", postgresql.JSONB(), nullable=True),
        sa.Column("timezone", sa.String(100), nullable=True),
        sa.Column("ai_instructions", sa.Text(), nullable=True),
    )
    op.create_index("ix_company_profiles_owner_user_id", "company_profiles", ["owner_user_id"])

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("keywords", postgresql.JSONB(), nullable=True),
        sa.Column("hs_code", sa.String(20), nullable=True),
        sa.Column("image_urls", postgresql.JSONB(), nullable=True),
        sa.Column("status", product_status, nullable=False, server_default="active"),
        sa.Column("applications", postgresql.JSONB(), nullable=True),
        sa.Column("specifications", postgresql.JSONB(), nullable=True),
        sa.Column("packaging", sa.String(500), nullable=True),
        sa.Column("moq", sa.String(255), nullable=True),
        sa.Column("lead_time", sa.String(255), nullable=True),
        sa.Column("production_capacity", sa.String(500), nullable=True),
    )
    op.create_index("ix_products_company_profile_id", "products", ["company_profile_id"])

    op.create_table(
        "knowledge_base",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
    )
    op.create_index("ix_knowledge_base_company_profile_id", "knowledge_base", ["company_profile_id"])

    op.create_table(
        "workspace_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("default_timezone", sa.String(100), nullable=True),
        sa.Column("default_language_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("languages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("default_currency_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("currencies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("date_format", date_format, nullable=False, server_default="YYYY-MM-DD"),
        sa.Column("time_format", time_format, nullable=False, server_default="24h"),
        sa.UniqueConstraint("owner_user_id"),
    )

    # --- extend the existing icp_criteria table (additive only; new FK is
    # nullable defensively in case this table already has rows in some
    # deployment, even though no CRUD API has ever written to it) --------
    op.add_column("icp_criteria", sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_icp_criteria_company_profile_id", "icp_criteria", ["company_profile_id"])
    op.add_column("icp_criteria", sa.Column("preferred_company_size", postgresql.JSONB(), nullable=True))
    op.add_column("icp_criteria", sa.Column("minimum_confidence_score", sa.Float(), nullable=True))
    op.add_column("icp_criteria", sa.Column("exclude_duplicate_companies", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("icp_criteria", sa.Column("search_depth", search_depth, nullable=False, server_default="standard"))
    op.add_column("icp_criteria", sa.Column("search_frequency", search_frequency, nullable=False, server_default="manual"))

    # --- timezone/scheduling columns on existing companies/contacts;
    # unused until a later milestone, added now so no further schema
    # change is needed for it. --------------------------------------------
    op.add_column("companies", sa.Column("timezone", sa.String(100), nullable=True))
    op.add_column("companies", sa.Column("working_days", postgresql.JSONB(), nullable=True))
    op.add_column("companies", sa.Column("business_hours", postgresql.JSONB(), nullable=True))

    op.add_column("contacts", sa.Column("timezone", sa.String(100), nullable=True))
    op.add_column("contacts", sa.Column("working_hours", postgresql.JSONB(), nullable=True))
    op.add_column("contacts", sa.Column("preferred_contact_time", postgresql.JSONB(), nullable=True))

    # --- junction tables --------------------------------------------------
    op.create_table(
        "company_profile_industries",
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profiles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("industry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("industries.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "icp_criteria_target_buyer_types",
        sa.Column("icp_criteria_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("icp_criteria.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("buyer_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buyer_types.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "icp_criteria_target_markets",
        sa.Column("icp_criteria_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("icp_criteria.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("country_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("countries.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "icp_criteria_excluded_countries",
        sa.Column("icp_criteria_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("icp_criteria.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("country_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("countries.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "icp_criteria_languages",
        sa.Column("icp_criteria_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("icp_criteria.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("language_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("languages.id", ondelete="CASCADE"), primary_key=True),
    )

    # --- seed data ---------------------------------------------------------
    countries_table = sa.table(
        "countries",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("region", sa.String),
    )
    country_rows = [
        # Europe
        ("DE", "Germany", "Europe"), ("FR", "France", "Europe"), ("IT", "Italy", "Europe"),
        ("ES", "Spain", "Europe"), ("GB", "United Kingdom", "Europe"), ("NL", "Netherlands", "Europe"),
        ("BE", "Belgium", "Europe"), ("PL", "Poland", "Europe"), ("PT", "Portugal", "Europe"),
        ("SE", "Sweden", "Europe"), ("AT", "Austria", "Europe"), ("CH", "Switzerland", "Europe"),
        ("IE", "Ireland", "Europe"), ("DK", "Denmark", "Europe"), ("NO", "Norway", "Europe"),
        ("FI", "Finland", "Europe"), ("GR", "Greece", "Europe"), ("CZ", "Czech Republic", "Europe"),
        ("RO", "Romania", "Europe"), ("HU", "Hungary", "Europe"),
        # Middle East
        ("AE", "United Arab Emirates", "Middle East"), ("SA", "Saudi Arabia", "Middle East"),
        ("QA", "Qatar", "Middle East"), ("KW", "Kuwait", "Middle East"), ("BH", "Bahrain", "Middle East"),
        ("OM", "Oman", "Middle East"), ("IL", "Israel", "Middle East"), ("JO", "Jordan", "Middle East"),
        ("LB", "Lebanon", "Middle East"), ("TR", "Turkey", "Middle East"),
        # North Africa
        ("EG", "Egypt", "North Africa"), ("MA", "Morocco", "North Africa"),
        ("TN", "Tunisia", "North Africa"), ("DZ", "Algeria", "North Africa"), ("LY", "Libya", "North Africa"),
    ]
    op.bulk_insert(
        countries_table,
        [{"id": uuid.uuid4(), "code": code, "name": name, "region": region} for code, name, region in country_rows],
    )

    buyer_types_table = sa.table("buyer_types", sa.column("id", postgresql.UUID(as_uuid=True)), sa.column("name", sa.String))
    buyer_type_names = [
        "Importers", "Distributors", "Wholesalers", "Retail Chains", "Textile Converters",
        "Garment Manufacturers", "Home Textile Manufacturers", "Brands", "Buying Offices",
    ]
    op.bulk_insert(buyer_types_table, [{"id": uuid.uuid4(), "name": name} for name in buyer_type_names])

    industries_table = sa.table("industries", sa.column("id", postgresql.UUID(as_uuid=True)), sa.column("name", sa.String))
    industry_names = [
        "Apparel & Fashion", "Home Textiles", "Technical Textiles", "Furnishing & Upholstery",
        "Denim", "Knitwear", "Textile Trading & Distribution", "Automotive Textiles",
        "Institutional & Hospitality Textiles",
    ]
    op.bulk_insert(industries_table, [{"id": uuid.uuid4(), "name": name} for name in industry_names])

    languages_table = sa.table(
        "languages", sa.column("id", postgresql.UUID(as_uuid=True)), sa.column("code", sa.String), sa.column("name", sa.String)
    )
    language_rows = [
        ("en", "English"), ("de", "German"), ("fr", "French"), ("es", "Spanish"), ("it", "Italian"),
        ("ar", "Arabic"), ("pt", "Portuguese"), ("nl", "Dutch"), ("tr", "Turkish"),
    ]
    op.bulk_insert(languages_table, [{"id": uuid.uuid4(), "code": code, "name": name} for code, name in language_rows])

    currencies_table = sa.table(
        "currencies", sa.column("id", postgresql.UUID(as_uuid=True)), sa.column("code", sa.String),
        sa.column("name", sa.String), sa.column("symbol", sa.String),
    )
    currency_rows = [
        ("USD", "US Dollar", "$"), ("EUR", "Euro", "€"), ("GBP", "British Pound", "£"),
        ("AED", "UAE Dirham", "AED"), ("SAR", "Saudi Riyal", "SAR"), ("TRY", "Turkish Lira", "₺"),
        ("EGP", "Egyptian Pound", "EGP"),
    ]
    op.bulk_insert(
        currencies_table,
        [{"id": uuid.uuid4(), "code": code, "name": name, "symbol": symbol} for code, name, symbol in currency_rows],
    )


def downgrade() -> None:
    op.drop_table("icp_criteria_languages")
    op.drop_table("icp_criteria_excluded_countries")
    op.drop_table("icp_criteria_target_markets")
    op.drop_table("icp_criteria_target_buyer_types")
    op.drop_table("company_profile_industries")

    op.drop_column("contacts", "preferred_contact_time")
    op.drop_column("contacts", "working_hours")
    op.drop_column("contacts", "timezone")

    op.drop_column("companies", "business_hours")
    op.drop_column("companies", "working_days")
    op.drop_column("companies", "timezone")

    op.drop_column("icp_criteria", "search_frequency")
    op.drop_column("icp_criteria", "search_depth")
    op.drop_column("icp_criteria", "exclude_duplicate_companies")
    op.drop_column("icp_criteria", "minimum_confidence_score")
    op.drop_column("icp_criteria", "preferred_company_size")
    op.drop_index("ix_icp_criteria_company_profile_id", table_name="icp_criteria")
    op.drop_column("icp_criteria", "company_profile_id")

    op.drop_table("workspace_settings")
    op.drop_table("knowledge_base")
    op.drop_table("products")
    op.drop_table("company_profiles")
    op.drop_table("currencies")
    op.drop_table("languages")
    op.drop_table("countries")
    op.drop_table("industries")
    op.drop_table("buyer_types")

    bind = op.get_bind()
    postgresql.ENUM(name="time_format", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="date_format", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="search_frequency", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="search_depth", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="product_status", create_type=False).drop(bind, checkfirst=True)
