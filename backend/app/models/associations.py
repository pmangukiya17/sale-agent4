"""
Plain many-to-many association tables (no extra columns of their own), kept
in one file so CompanyProfile/Industry/ICPCriteria/BuyerType/Country/Language
don't need to import each other just to reference a junction table.
"""
from sqlalchemy import Column, ForeignKey, Table
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base

company_profile_industries = Table(
    "company_profile_industries",
    Base.metadata,
    Column("company_profile_id", UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("industry_id", UUID(as_uuid=True), ForeignKey("industries.id", ondelete="CASCADE"), primary_key=True),
)

icp_criteria_target_buyer_types = Table(
    "icp_criteria_target_buyer_types",
    Base.metadata,
    Column("icp_criteria_id", UUID(as_uuid=True), ForeignKey("icp_criteria.id", ondelete="CASCADE"), primary_key=True),
    Column("buyer_type_id", UUID(as_uuid=True), ForeignKey("buyer_types.id", ondelete="CASCADE"), primary_key=True),
)

icp_criteria_target_markets = Table(
    "icp_criteria_target_markets",
    Base.metadata,
    Column("icp_criteria_id", UUID(as_uuid=True), ForeignKey("icp_criteria.id", ondelete="CASCADE"), primary_key=True),
    Column("country_id", UUID(as_uuid=True), ForeignKey("countries.id", ondelete="CASCADE"), primary_key=True),
)

icp_criteria_excluded_countries = Table(
    "icp_criteria_excluded_countries",
    Base.metadata,
    Column("icp_criteria_id", UUID(as_uuid=True), ForeignKey("icp_criteria.id", ondelete="CASCADE"), primary_key=True),
    Column("country_id", UUID(as_uuid=True), ForeignKey("countries.id", ondelete="CASCADE"), primary_key=True),
)

icp_criteria_languages = Table(
    "icp_criteria_languages",
    Base.metadata,
    Column("icp_criteria_id", UUID(as_uuid=True), ForeignKey("icp_criteria.id", ondelete="CASCADE"), primary_key=True),
    Column("language_id", UUID(as_uuid=True), ForeignKey("languages.id", ondelete="CASCADE"), primary_key=True),
)

# M2 Phase 1b: backs ICPCriteria.target_industries - the scoring engine's
# new industry_match factor (app/discovery/scoring.py) and the API's
# target_industry_ids field. Same shape as every other ICPCriteria
# junction table above.
icp_criteria_target_industries = Table(
    "icp_criteria_target_industries",
    Base.metadata,
    Column("icp_criteria_id", UUID(as_uuid=True), ForeignKey("icp_criteria.id", ondelete="CASCADE"), primary_key=True),
    Column("industry_id", UUID(as_uuid=True), ForeignKey("industries.id", ondelete="CASCADE"), primary_key=True),
)
