import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import WorkflowStepInvocationStatus


class WorkflowStepInvocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One actual step-execution ATTEMPT - the audit trail that makes the
    Workflow Engine explainable (see docs/architecture/
    m7-workflow-engine-plan.md section 7). Append-only: a retry of the
    same step is a NEW row with `attempt_number` incremented, never an
    update to the previous attempt's row - the full retry history stays
    permanently inspectable, matching the DeliveryEvent/OutreachEdit
    append-only precedent already established elsewhere in this
    codebase.

    `action_key` is copied from the step_graph at the moment this
    attempt started, not re-derived later - if a step's action_key were
    ever somehow different when read back (it can't be, since the
    instance's pinned WorkflowDefinition version is immutable per the
    Compatibility Policy, but this is belt-and-suspenders), this row
    still records exactly what was actually invoked for THIS attempt.

    `input_snapshot` is the ActionInput's `context` at the moment this
    attempt started (opaque JSONB, a debugging/explainability copy, not
    a live reference); `output` is the resulting ActionOutput's `result`
    (also opaque). `error` is populated only for FAILED - the
    ActionOutput's `error` string, stored verbatim.

    `status` is WorkflowStepInvocationStatus - see that enum's own
    docstring for why it is deliberately NOT the same vocabulary as
    app.workflow_engine.actions.base.ActionOutcome.
    """

    __tablename__ = "workflow_step_invocations"

    workflow_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )

    step_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action_key: Mapped[str] = mapped_column(String(255), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    status: Mapped[WorkflowStepInvocationStatus] = mapped_column(
        Enum(
            WorkflowStepInvocationStatus,
            name="workflow_step_invocation_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )

    input_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    workflow_instance: Mapped["WorkflowInstance"] = relationship()
