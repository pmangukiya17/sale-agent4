"""Fix CASCADE-into-execution-history FKs: change to RESTRICT.

Found during the M8.16/M8.17 comprehensive verification pass (Track A,
FK/ondelete audit), extending the same check that was applied to
Discovery Search during M8.17. Both findings share one root cause: a
still-deletable configuration/detail row cascading into a table this
platform treats as permanent, explainable execution history - directly
conflicting with the project's standing "explainability, auditability,
AI traceability" principles. See
docs/architecture/deferred-items-and-design-boundaries.md for the full
writeup, including why SET NULL was considered and rejected for every
one of these seven columns (all are `nullable=False` - SET NULL would
require also loosening that constraint, a bigger and separately-scoped
change; RESTRICT needs no column change at all).

Seven FKs, two families:

1. DiscoverySearch -> DiscoveryJob/DiscoveryRun (the original M8.17
   finding, left unfixed at the time pending this migration):
   - discovery_jobs.discovery_search_id
   - discovery_runs.discovery_search_id
     (DiscoveryRun's own docstring calls itself a "frozen, permanent
     record" - CASCADE directly contradicted that guarantee.)

2. ProspectContact -> Outreach/Delivery execution history (found during
   the Track A audit, more severe than the Discovery Search case - it
   touches an entire domain's audit trail, not one domain's job/run
   pair):
   - delivery_queue_items.prospect_contact_id (real send history)
   - outreach_drafts.prospect_contact_id
   - outreach_requests.prospect_contact_id
   - outreach_jobs.prospect_contact_id
   - outreach_runs.prospect_contact_id
     (OutreachRun's own docstring also calls itself a "Frozen, permanent
     record" - same violation as DiscoveryRun.)

All seven constraint names below are Postgres's own default
`{table}_{column}_fkey` naming (none of these were created with an
explicit `name=` in their original migration, so Postgres auto-named
them at CREATE TABLE time).

No application code needs to change for this migration alone - it only
tightens a database-level guarantee. The two routes that could actually
trigger the new RESTRICT (delete_discovery_search, delete_prospect_contact)
get their own IntegrityError -> clean 400 handling in a separate,
API-layer commit, mirroring delete_outreach_playbook's existing pattern.

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (constraint_name, source_table, source_column, target_table)
_FK_FIXES = [
    ("discovery_jobs_discovery_search_id_fkey", "discovery_jobs", "discovery_search_id", "discovery_searches"),
    ("discovery_runs_discovery_search_id_fkey", "discovery_runs", "discovery_search_id", "discovery_searches"),
    ("delivery_queue_items_prospect_contact_id_fkey", "delivery_queue_items", "prospect_contact_id", "prospect_contacts"),
    ("outreach_drafts_prospect_contact_id_fkey", "outreach_drafts", "prospect_contact_id", "prospect_contacts"),
    ("outreach_requests_prospect_contact_id_fkey", "outreach_requests", "prospect_contact_id", "prospect_contacts"),
    ("outreach_jobs_prospect_contact_id_fkey", "outreach_jobs", "prospect_contact_id", "prospect_contacts"),
    ("outreach_runs_prospect_contact_id_fkey", "outreach_runs", "prospect_contact_id", "prospect_contacts"),
]


def upgrade() -> None:
    for name, table, column, target in _FK_FIXES:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, target, [column], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    # Restores the exact original CASCADE behavior - see this file's own
    # docstring for why that behavior was unsafe; this exists purely for
    # migration reversibility, not because CASCADE should ever be
    # reinstated in practice.
    for name, table, column, target in _FK_FIXES:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, target, [column], ["id"], ondelete="CASCADE")
