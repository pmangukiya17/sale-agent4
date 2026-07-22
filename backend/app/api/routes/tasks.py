import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.enums import TaskStatus
from app.models.task import Task
from app.schemas.task import TaskRead

router = APIRouter()

# CRM Automation milestone. Tasks (Recommended Actions) are created
# EXCLUSIVELY by app.crm_automation.service, from deterministic rules -
# these routes never create one. The only write actions here are
# complete/dismiss (a human acting on an AI recommendation), mirroring
# the "AI recommends, human decides" shape already established by
# OutreachDraft's approve/reject routes - never a route that lets a
# caller invent a Task's content.


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/company-profiles/{company_profile_id}/tasks", response_model=list[TaskRead])
def list_tasks(
    prospect_id: uuid.UUID | None = Query(None),
    conversation_id: uuid.UUID | None = Query(None),
    status_filter: TaskStatus | None = Query(None, alias="status"),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[Task]:
    stmt = select(Task).where(Task.company_profile_id == profile.id).order_by(Task.created_at.desc())
    if prospect_id is not None:
        stmt = stmt.where(Task.prospect_id == prospect_id)
    if conversation_id is not None:
        stmt = stmt.where(Task.conversation_id == conversation_id)
    if status_filter is not None:
        stmt = stmt.where(Task.status == status_filter)
    return list(db.scalars(stmt).all())


def _get_task_or_404(db: Session, profile_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.post("/company-profiles/{company_profile_id}/tasks/{task_id}/complete", response_model=TaskRead)
def complete_task(
    task_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Task:
    task = _get_task_or_404(db, profile.id, task_id)
    task.status = TaskStatus.COMPLETED
    task.resolved_at = _now()
    db.commit()
    db.refresh(task)
    return task


@router.post("/company-profiles/{company_profile_id}/tasks/{task_id}/dismiss", response_model=TaskRead)
def dismiss_task(
    task_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Task:
    task = _get_task_or_404(db, profile.id, task_id)
    task.status = TaskStatus.DISMISSED
    task.resolved_at = _now()
    db.commit()
    db.refresh(task)
    return task
