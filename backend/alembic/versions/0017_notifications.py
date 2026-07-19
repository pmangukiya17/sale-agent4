"""M8.5 Event Backbone: Notification Center.

Adds `notifications` (the user-facing consumer of the platform Event
stream) and `notification_dispatches` (the Notification worker's own
idempotency/decision-tracking table, mirroring `event_consumptions`'
role for the Event Dispatcher worker exactly - see both models' own
docstrings in app/models/notification.py).

Zero changes to `events` beyond what migration 0016 already added -
notifications.event_id is a plain FK (ondelete=RESTRICT, matching
event_consumptions.event_id's own convention: events are append-only and
must never be deletable out from under something that references them).

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "company_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(50), nullable=False, server_default="medium"),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notifications_company_profile_id", "notifications", ["company_profile_id"])
    op.create_index("ix_notifications_event_id", "notifications", ["event_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])

    op.create_table(
        "notification_dispatches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=False),
    )
    # One unique index, not a unique index plus a redundant plain one -
    # it already serves the worker's own by-event_id lookups (matching
    # migration 0013's own "no extra, redundant single-column indexes"
    # discipline).
    op.create_index(
        "uq_notification_dispatches_event_id", "notification_dispatches", ["event_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_notification_dispatches_event_id", table_name="notification_dispatches")
    op.drop_table("notification_dispatches")

    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_notifications_event_id", table_name="notifications")
    op.drop_index("ix_notifications_company_profile_id", table_name="notifications")
    op.drop_table("notifications")
