"""M2 Phase 1c: Discovery Job graceful cancellation.

CEO-approved scope (Phase 1c: Prospect -> Opportunity Import + Discovery
Job Cancellation). Adds exactly two nullable, purely additive columns to
discovery_jobs - a cancellation is a REQUEST, recorded separately from
DiscoveryJob.status (which stays owned exclusively by
app.discovery.pipeline.run_discovery_search(), the same single-writer
discipline every other DiscoveryJob column already follows):

- cancel_requested_at: when a human asked for this job to stop. NULL
  means "never requested." Checked by the pipeline's own provider/
  candidate loops (see pipeline.py) at safe checkpoints between units of
  work - a currently-executing provider call is never interrupted
  mid-call (this sandbox does not add multi-process signal/interrupt
  plumbing that doesn't exist anywhere else in this codebase), only
  between one candidate/provider and the next. Cancellation is
  deliberately NOT modeled as an immediate DiscoveryJobStatus.CANCELLED
  write from the API layer - only the worker actually running the job
  (which alone knows what has and hasn't been safely committed yet) is
  allowed to transition status to CANCELLED, exactly mirroring how
  status already only ever moves through COMPLETED/PARTIALLY_COMPLETED/
  FAILED from inside that same function, never from a route.
- cancel_requested_by_user_id: audit - who asked. Nullable, ON DELETE
  SET NULL, matching Prospect.reviewed_by_user_id's existing pattern
  (losing the user record shouldn't erase that a cancellation was
  requested, just who did it).

No Opportunity-side migration: Prospect -> Opportunity Import needs zero
schema change - Opportunity.prospect_id has existed since Track C3, and
idempotency is enforced by a query (does an Opportunity for this
prospect_id already exist), not a new unique constraint - see
docs/architecture (or the Phase 1c completion summary) for why a DB-
level UNIQUE(prospect_id) constraint was deliberately NOT added here:
Opportunity's own docstring already documents company_profile_id +
prospect_id as a many-times-reusable pair implicitly (nothing before
this phase assumed at most one Opportunity per Prospect), and a future
legitimate case - re-opening a second deal with a repeat customer after
the first Opportunity closed - would violate a hard uniqueness
constraint. The service-layer idempotency check achieves "multiple
imports never create duplicate Opportunities" without foreclosing that
future case.

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("discovery_jobs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "discovery_jobs",
        sa.Column("cancel_requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "discovery_jobs_cancel_requested_by_user_id_fkey",
        "discovery_jobs",
        "users",
        ["cancel_requested_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("discovery_jobs_cancel_requested_by_user_id_fkey", "discovery_jobs", type_="foreignkey")
    op.drop_column("discovery_jobs", "cancel_requested_by_user_id")
    op.drop_column("discovery_jobs", "cancel_requested_at")
