import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import WorkflowInstanceStatus


class WorkflowInstance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One running (or completed) execution of a WorkflowDefinition - see
    docs/architecture/m7-workflow-engine-plan.md section 3 (Workflow
    Instances) and section 4 (state machine).

    `workflow_definition_id` + `version` together are the permanent
    version pin, set ONCE at creation (by the Event Dispatcher worker,
    Part 1 Phase 4, from resolve_active_definition()'s result at the
    moment a trigger event matched) and NEVER changed afterward, for the
    entire life of this row - this is the hard invariant the approved
    Compatibility Policy requires: "Existing Workflow Instances always
    remain pinned to the exact definition version they started with...
    There must never be automatic or manual engine-driven migration of
    running Workflow Instances to another definition version." `version`
    is a plain Integer column here, not derived by joining to
    workflow_definitions.version at read time - even after the
    definition this instance is pinned to is later DEPRECATED (or,
    hypothetically, if some future bug ever let a definition row's
    version-adjacent data drift), this instance's own pinned `version`
    value is the durable source of truth for "which version am I
    running," independent of the definition row's current state.

    `status` is WorkflowInstanceStatus - see that enum's own docstring
    for the full lifecycle. `current_step_id` names a key into the
    pinned definition's `step_graph.steps` - set at creation to
    `step_graph.start_step_id` and advanced only by the Step Runner
    worker (Part 1, Phase 5) following a step's `transitions.success`/
    `transitions.failure` rule. Not nullable - an instance always knows
    which step it's on (or, once terminal, which step it ended on), even
    in COMPLETED/FAILED/CANCELLED status - this row is never wiped back
    to an unknown state.

    `context` is the instance's own accumulated, opaque JSONB working
    data - the engine passes each Action's `result` back into this blob
    as a pure pass-through (see app.workflow_engine.actions.base.
    ActionOutput); it never reads or validates individual keys itself,
    except one reserved, engine-owned key documented in step_runner_
    worker.py (Part 1, Phase 5): `_woken_by_event`, written by the Event
    Dispatcher when resuming a WAITING instance, consumed and cleared by
    the built-in wait-for-event pseudo-action on the Step Runner's next
    pass. Defaults to an empty object, never null, so callers never need
    a None-check before reading from it.

    `claimed_by`/`claimed_at` are concurrency-safety columns, not
    business data - declared now even though only one Step Runner
    replica exists in this project's current deployment, because a
    claim column is structural plumbing a future multi-replica
    deployment needs from day one, not something that can be added
    later without a migration in between (see docs/architecture/
    m7-workflow-engine-plan.md section 5's own explicit exception to
    this project's usual "don't add anticipatory schema" discipline).

    `subject_type`/`subject_id` are opaque correlation keys, same
    treatment as Event's own columns - never interpreted by the engine,
    only used for correlation/explainability and for the Event
    Dispatcher's resume-matching (an instance waiting on a subject_id
    only resumes on an event carrying a matching subject_id, or either
    being null treated as a wildcard - see event_dispatcher_worker.py).

    One-directional relationships only toward WorkflowDefinition/
    CompanyProfile, matching the "point up, never down" boundary already
    established by Conversation/EmailMessage elsewhere in this codebase.
    """

    __tablename__ = "workflow_instances"

    workflow_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_definitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    subject_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    status: Mapped[WorkflowInstanceStatus] = mapped_column(
        Enum(
            WorkflowInstanceStatus,
            name="workflow_instance_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=WorkflowInstanceStatus.PENDING,
        nullable=False,
        index=True,
    )
    current_step_id: Mapped[str] = mapped_column(String(255), nullable=False)

    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    workflow_definition: Mapped["WorkflowDefinition"] = relationship()
    company_profile: Mapped["CompanyProfile"] = relationship()
