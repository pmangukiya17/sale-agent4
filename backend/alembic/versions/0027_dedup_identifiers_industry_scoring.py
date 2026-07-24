"""M2 Phase 1b: government identifier dedup fields + ICP target industries.

CEO-approved architecture (see docs/architecture/
m2-phase1b-dedup-scoring-architecture.md and the CEO's Phase 1b
architecture-review approval message): VAT number and Registration
Number are the strongest dedup signal, checked before website/domain
(tier 2) and fuzzy name+country (tier 3). They are modeled as two
separate, independently-indexed nullable columns on Prospect - not one
combined "identifier" column - so that a future third/fourth identifier
type (Company Number, EIN, Business Registration ID, ...) can be added
the same way later without redesigning the lookup layer (see
app/discovery/identifier_lookup.py, added alongside this migration).

email is also added here (nullable, not indexed) - a company-level
contact email surfaced by a provider, distinct from
ProspectContact.email (a specific person's email) and NOT used as a
dedup signal (see the architecture doc's explicit recommendation
against company-level email as a dedup key - too easy for two
different real companies to share a generic inbox).

icp_criteria_target_industries is a new junction table, added using the
exact same shape as the four existing ICPCriteria junction tables
(icp_criteria_target_buyer_types/target_markets/excluded_countries/
languages - see app/models/associations.py) - plain two-column table,
both columns primary_key + ForeignKey(..., ondelete="CASCADE"), no
extra columns. This is what backs the scoring engine's new fifth
factor (industry_match) and the API's new target_industry_ids field.

No new column for configurable scoring weights - per the CEO's explicit
direction, ICPCriteria.rules (the existing JSONB escape hatch) is
reused, storing an optional `rules["scoring_weights"]` dict. Nothing to
migrate for that.

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("prospects", sa.Column("vat_number", sa.String(100), nullable=True))
    op.create_index("ix_prospects_vat_number", "prospects", ["vat_number"])

    op.add_column("prospects", sa.Column("registration_number", sa.String(100), nullable=True))
    op.create_index("ix_prospects_registration_number", "prospects", ["registration_number"])

    # Company-level contact email - not indexed, not a dedup signal (see
    # this migration's own docstring / the architecture doc).
    op.add_column("prospects", sa.Column("email", sa.String(255), nullable=True))

    op.create_table(
        "icp_criteria_target_industries",
        sa.Column("icp_criteria_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("icp_criteria.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("industry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("industries.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("icp_criteria_target_industries")

    op.drop_column("prospects", "email")

    op.drop_index("ix_prospects_registration_number", table_name="prospects")
    op.drop_column("prospects", "registration_number")

    op.drop_index("ix_prospects_vat_number", table_name="prospects")
    op.drop_column("prospects", "vat_number")
