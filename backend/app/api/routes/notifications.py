import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_owned_company_profile
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.notification import Notification
from app.schemas.notification import NotificationMarkAllReadResult, NotificationRead

router = APIRouter()

# Notifications are read/updated (read-state only) here - they are never
# created through this router. Creation is exclusively the Notification
# worker's job (app.notifications.worker), which consumes the Event
# stream - see that package's own docstring. This mirrors the same
# "one sanctioned write path, many read paths" discipline
# publish_event()/Event already established.


@router.get("/company-profiles/{company_profile_id}/notifications", response_model=list[NotificationRead])
def list_notifications(
    is_read: bool | None = Query(None),
    limit: int = Query(50, le=200),
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> list[Notification]:
    stmt = select(Notification).where(Notification.company_profile_id == profile.id)
    if is_read is not None:
        stmt = stmt.where(Notification.is_read == is_read)
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def _get_notification_or_404(db: Session, profile_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.company_profile_id != profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification


@router.post(
    "/company-profiles/{company_profile_id}/notifications/{notification_id}/read",
    response_model=NotificationRead,
)
def mark_notification_read(
    notification_id: uuid.UUID,
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> Notification:
    notification = _get_notification_or_404(db, profile.id, notification_id)
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notification)
    return notification


@router.post(
    "/company-profiles/{company_profile_id}/notifications/mark-all-read",
    response_model=NotificationMarkAllReadResult,
)
def mark_all_notifications_read(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> NotificationMarkAllReadResult:
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(Notification)
        .where(Notification.company_profile_id == profile.id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=now)
    )
    db.commit()
    return NotificationMarkAllReadResult(marked_count=result.rowcount or 0)
