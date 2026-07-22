import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TaskPriority, TaskStatus


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A persisted Recommended Action - CRM Automation milestone (deferred
    scope from docs/architecture/m6-reply-intelligence-plan.md section 2,
    adjusted at approval time). Created exclusively by
    app.crm_automation.service, from deterministic rules in
    app.crm_automation.state_machine - never fabricated by the frontend,
    which only ever reads these rows (see Conversations.tsx's own
    docstring for that boundary).

    Deliberately drops the original doc's `reply_analysis_id` FK - that
    table (a per-message AI analysis history) was explicitly rejected at
    M6.4's real approval in favor of Conversation's own rolling
    reply_status/needs_human_review fields; a Task's provenance is
    instead `source_event_type`, a free string identifying which
    deterministic rule created it (e.g. "reply_classified",
    "relationship_stage_advanced") - enough for explainability without a
    dangling FK to a table that doesn't exist.

    company_profile_id is required (the tenant/"workspace" scope, per
    this project's existing multi-business vocabulary - there is no
    separate literal Workspace entity; CompanyProfile is it).
    prospect_id is required (a Task is always about one account).
    prospect_contact_id and conversation_id are both nullable: some tasks
    are account-level (e.g. a relationship_stage advance with no single
    message behind it), not every task originates from one specific
    contact or thread.

    assigned_user_id is nullable and deliberately UNUSED in this
    milestone - included now, written by nothing, so the future M9
    Organization & AI Workforce Management milestone (task assignment
    across a multi-user team) needs zero migration to add it later. This
    is the one deliberately-anticipatory field in this table; every other
    column here is real, load-bearing, and used starting from this
    milestone.
    """

    __tablename__ = "tasks"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prospect_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospect_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Future M9 field - unused today, see this model's own docstring.
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(
            TaskPriority,
            name="task_priority",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=TaskPriority.NORMAL,
        nullable=False,
        index=True,
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    company_profile: Mapped["CompanyProfile"] = relationship()
    prospect: Mapped["Prospect"] = relationship()
    prospect_contact: Mapped["ProspectContact | None"] = relationship()
    conversation: Mapped["Conversation | None"] = relationship()
    assigned_user: Mapped["User | None"] = relationship()
