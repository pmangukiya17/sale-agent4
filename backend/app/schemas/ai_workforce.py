import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

# --- M8.4 backend addition: AI Workforce domain API ---------------------
# These are the frontend-facing contracts - deliberately NOT a re-export of
# WorkflowInstanceStatus/WorkflowStepInvocationStatus (app.models.enums).
# See app/ai_workforce/mapper.py's own docstring for the full reasoning:
# the frontend's "AI Workforce" concept should outlive whatever execution
# engine happens to sit underneath it today (the M7 Workflow Engine).


class AgentActivityState(str, enum.Enum):
    """The AI Workforce's own, small, honest state vocabulary - NOT the
    Design Bible's full illustrative 12-word list (Idle/Thinking/
    Researching/Reading/Writing/Scoring/Waiting/Reviewing/Running/
    Completed/Paused/Failed). Today's WorkflowInstanceStatus only records
    STRUCTURAL execution state, never a semantic "what kind of work is
    happening" verb - inventing "Thinking" vs "Researching" from a status
    enum that can't distinguish them would be fabricating data. A future
    milestone that wants the fuller verb vocabulary needs the engine to
    actually record semantic activity-type metadata first; until then,
    this is the real, current truth, one level up from raw storage:

    QUEUED - created, not yet picked up by a worker.
    RUNNING - actively being processed right now.
    WAITING - suspended, waiting on a real trigger (time/event/human
    approval) - not consuming attempts, not a synonym for "stuck".
    PAUSED - an operator-driven suspension. Schema-real
    (WorkflowInstanceStatus.SUSPENDED exists today) but currently DORMANT
    - no code path in this codebase ever sets it yet, same disclosed gap
    StatusIndicator.tsx's own "paused" state already documents on the
    frontend.
    COMPLETED / FAILED / CANCELLED - terminal, matches the underlying
    engine's own terminal states exactly.
    """

    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentActivityTraceStatus(str, enum.Enum):
    """One entry in an AgentActivity's trace (today: one
    WorkflowStepInvocation row). Kept as its own small enum, not a direct
    re-export of WorkflowStepInvocationStatus, for the same
    storage-vs-domain isolation reason as AgentActivityState above - even
    though the words happen to match today."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentActivityRead(BaseModel):
    """One unit of AI-driven work the AI Workforce page shows as a card.
    Today, exactly one AgentActivity = one WorkflowInstance row (see
    app/ai_workforce/mapper.py) - that 1:1 relationship is an
    implementation detail of TODAY's mapping, not a guarantee this
    contract makes forever."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    workflow_key: str
    state: AgentActivityState
    current_step_id: str
    current_action_key: str | None
    subject_type: str | None
    subject_id: uuid.UUID | None
    started_at: datetime | None
    updated_at: datetime
    completed_at: datetime | None
    created_at: datetime


class AgentActivityTraceEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_activity_id: uuid.UUID
    step_id: str
    action_key: str
    attempt_number: int
    status: AgentActivityTraceStatus
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
