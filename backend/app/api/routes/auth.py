import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserRead

router = APIRouter()


@router.post("/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, request: Request, db: Session = Depends(get_db)) -> User:
    """
    Create a new user account.

    INTERIM, pending M9 Organization & AI Workforce Management: this
    project has no organization-scoped invitation/membership system yet,
    so this endpoint is the only way any account gets created. M9 is
    expected to replace it with org-scoped invites, at which point this
    endpoint (and the bootstrap exception below) should be removed
    entirely rather than extended.

    Gated behind admin authorization, with one deliberate exception: if
    zero users exist yet (a brand-new deployment), registration is open
    and the very first account created is automatically granted
    UserRole.ADMIN. Without this exception, a fresh install would have no
    way to create its first admin at all - there is no seed script or
    CLI for this today. Every registration after that first one requires
    a valid admin bearer token, checked manually here (not via the
    get_current_active_admin dependency) so the bootstrap case can skip
    the auth requirement entirely rather than failing 401 on a request
    with no token.
    """
    is_bootstrap = db.query(User.id).first() is None

    if not is_bootstrap:
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip()
        payload = decode_access_token(token) if token else None
        caller = None
        if payload and payload.get("sub"):
            try:
                caller = db.get(User, uuid.UUID(payload["sub"]))
            except ValueError:
                caller = None
        if caller is None or not caller.is_active or caller.role != UserRole.ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")

    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hash_password(user_in.password),
        role=UserRole.ADMIN if is_bootstrap else UserRole.OPERATOR,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    access_token = create_access_token(subject=str(user.id))
    return Token(access_token=access_token)


@router.get("/auth/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
