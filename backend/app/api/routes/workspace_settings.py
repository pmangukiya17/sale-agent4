from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.currency import Currency
from app.models.language import Language
from app.models.user import User
from app.models.workspace_settings import WorkspaceSettings
from app.schemas.workspace_settings import WorkspaceSettingsRead, WorkspaceSettingsUpdate

router = APIRouter()


def _get_or_create(db: Session, user: User) -> WorkspaceSettings:
    settings = db.query(WorkspaceSettings).filter(WorkspaceSettings.owner_user_id == user.id).first()
    if settings is None:
        settings = WorkspaceSettings(owner_user_id=user.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("/workspace-settings", response_model=WorkspaceSettingsRead)
def get_workspace_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkspaceSettings:
    return _get_or_create(db, current_user)


@router.put("/workspace-settings", response_model=WorkspaceSettingsRead)
def update_workspace_settings(
    settings_in: WorkspaceSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkspaceSettings:
    settings = _get_or_create(db, current_user)

    if settings_in.default_language_id is not None:
        if db.get(Language, settings_in.default_language_id) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown language id")
    if settings_in.default_currency_id is not None:
        if db.get(Currency, settings_in.default_currency_id) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown currency id")

    for field, value in settings_in.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    db.commit()
    db.refresh(settings)
    return settings
