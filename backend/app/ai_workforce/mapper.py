import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import WorkflowInstanceStatus, WorkflowStepInvocationStatus
from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step_invocation import WorkflowStepInvocation
from app.schemas.ai_workforce import (
    AgentActivityRead,
    AgentActivityState,
    AgentActivityTraceEntryRead,
    AgentActivityTraceStatus,
)

# See app/ai_workforce/__init__.py for why this mapping is isolated here
# rather than inline in the route. _STATUS_MAP is the one place today's
# storage vocabulary (WorkflowInstanceStatus) meets the domain vocabulary
# (AgentActivityState) - if a future milestone changes what backs an
# AgentActivity, only this dict (and the query functions below it) change.
_STATUS_MAP: dict[WorkflowInstanceStatus, AgentActivityState] = {
    WorkflowInstanceStatus.PENDING: AgentActivityState.QUEUED,
    WorkflowInstanceStatus.RUNNING: AgentActivityState.RUNNING,
    WorkflowInstanceStatus.WAITING: AgentActivityState.WAITING,
    WorkflowInstanceStatus.SUSPENDED: AgentActivityState.PAUSED,
    WorkflowInstanceStatus.COMPLETED: AgentActivityState.COMPLETED,
    WorkflowInstanceStatus.FAILED: AgentActivityState.FAILED,
    WorkflowInstanceStatus.CANCELLED: AgentActivityState.CANCELLED,
}
_REVERSE_STATUS_MAP: dict[AgentActivityState, WorkflowInstanceStatus] = {
    domain: storage for storage, domain in _STATUS_MAP.items()
}

_TRACE_STATUS_MAP: dict[WorkflowStepInvocationStatus, AgentActivityTraceStatus] = {
    WorkflowStepInvocationStatus.PENDING: AgentActivityTraceStatus.PENDING,
    WorkflowStepInvocationStatus.RUNNING: AgentActivityTraceStatus.RUNNING,
    WorkflowStepInvocationStatus.SUCCEEDED: AgentActivityTraceStatus.SUCCEEDED,
    WorkflowStepInvocationStatus.FAILED: AgentActivityTraceStatus.FAILED,
    WorkflowStepInvocationStatus.SKIPPED: AgentActivityTraceStatus.SKIPPED,
}


def map_instance_status(instance_status: WorkflowInstanceStatus) -> AgentActivityState:
    return _STATUS_MAP[instance_status]


def _domain_state_to_storage_status(state: AgentActivityState) -> WorkflowInstanceStatus:
    return _REVERSE_STATUS_MAP[state]


def _latest_action_key(db: Session, instance_id: uuid.UUID) -> str | None:
    """The most recent WorkflowStepInvocation.action_key for this
    instance, if any exist yet - a PENDING instance the Step Runner
    hasn't claimed at all legitimately has none."""
    stmt = (
        select(WorkflowStepInvocation.action_key)
        .where(WorkflowStepInvocation.workflow_instance_id == instance_id)
        .order_by(WorkflowStepInvocation.created_at.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def _to_agent_activity(instance: WorkflowInstance, workflow_key: str, current_action_key: str | None) -> AgentActivityRead:
    return AgentActivityRead(
        id=instance.id,
        company_profile_id=instance.company_profile_id,
        workflow_key=workflow_key,
        state=map_instance_status(instance.status),
        current_step_id=instance.current_step_id,
        current_action_key=current_action_key,
        subject_type=instance.subject_type,
        subject_id=instance.subject_id,
        started_at=instance.started_at,
        updated_at=instance.updated_at,
        completed_at=instance.completed_at,
        created_at=instance.created_at,
    )


def list_agent_activities(
    db: Session,
    company_profile_id: uuid.UUID,
    *,
    state_filter: AgentActivityState | None = None,
    limit: int = 50,
) -> list[AgentActivityRead]:
    """The AI Workforce roster for one business - every AgentActivity
    currently reads as one WorkflowInstance row (see this module's own
    docstring for why that's a mapping detail, not a permanent contract).
    """
    stmt = (
        select(WorkflowInstance, WorkflowDefinition.key)
        .join(WorkflowDefinition, WorkflowInstance.workflow_definition_id == WorkflowDefinition.id)
        .where(WorkflowInstance.company_profile_id == company_profile_id)
    )
    if state_filter is not None:
        stmt = stmt.where(WorkflowInstance.status == _domain_state_to_storage_status(state_filter))
    stmt = stmt.order_by(WorkflowInstance.created_at.desc()).limit(limit)

    rows = db.execute(stmt).all()
    return [
        _to_agent_activity(instance, workflow_key, _latest_action_key(db, instance.id))
        for instance, workflow_key in rows
    ]


def get_agent_activity(
    db: Session, company_profile_id: uuid.UUID, activity_id: uuid.UUID
) -> AgentActivityRead | None:
    stmt = (
        select(WorkflowInstance, WorkflowDefinition.key)
        .join(WorkflowDefinition, WorkflowInstance.workflow_definition_id == WorkflowDefinition.id)
        .where(WorkflowInstance.id == activity_id, WorkflowInstance.company_profile_id == company_profile_id)
    )
    row = db.execute(stmt).first()
    if row is None:
        return None
    instance, workflow_key = row
    return _to_agent_activity(instance, workflow_key, _latest_action_key(db, instance.id))


def list_activity_trace(
    db: Session, company_profile_id: uuid.UUID, activity_id: uuid.UUID
) -> list[AgentActivityTraceEntryRead] | None:
    """Returns None (not an empty list) when the activity itself doesn't
    exist or isn't owned by this company profile, so the route can 404 -
    an empty list would incorrectly mean "found it, no trace entries yet."
    """
    instance = db.get(WorkflowInstance, activity_id)
    if instance is None or instance.company_profile_id != company_profile_id:
        return None

    stmt = (
        select(WorkflowStepInvocation)
        .where(WorkflowStepInvocation.workflow_instance_id == activity_id)
        .order_by(WorkflowStepInvocation.created_at.asc())
    )
    invocations = db.scalars(stmt).all()
    return [
        AgentActivityTraceEntryRead(
            id=inv.id,
            agent_activity_id=inv.workflow_instance_id,
            step_id=inv.step_id,
            action_key=inv.action_key,
            attempt_number=inv.attempt_number,
            status=_TRACE_STATUS_MAP[inv.status],
            error=inv.error,
            started_at=inv.started_at,
            completed_at=inv.completed_at,
            created_at=inv.created_at,
        )
        for inv in invocations
    ]
