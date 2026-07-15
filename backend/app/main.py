import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, companies, contacts, health
from app.core.config import settings
from app.core.security import hash_password
from app.db import base as _base  # noqa: F401  (imports every model so relationship() string refs resolve)
from app.db.session import SessionLocal
from app.models.enums import UserRole
from app.models.user import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sales_agent")


def ensure_first_admin() -> None:
    """
    Bootstrap a single admin user on first boot so there is always a way in,
    without exposing a public signup form. Safe to run on every startup —
    it's a no-op once any user exists.

    Note this is deliberately a one-time bootstrap, not a sync: if the
    "users" table already has rows (e.g. this is a Postgres volume that
    survived from an earlier run), this function does NOT touch existing
    passwords, even if FIRST_ADMIN_PASSWORD in .env has since changed. That
    mismatch — an existing user whose stored hash no longer matches the
    current .env value — is the most common cause of "the .env credentials
    don't authenticate" and is NOT a bug in this function; it means the
    database already has state from before. The fix is a truly clean
    database (`docker compose down -v`), not resetting the password here on
    every boot, which would be a surprising and unsafe default for anything
    that isn't a first-time bootstrap.
    """
    db = SessionLocal()
    try:
        existing_count = db.query(User).count()
        if existing_count > 0:
            logger.info(
                "Existing admin detected — skipping bootstrap (%d user(s) "
                "already exist in this database). If FIRST_ADMIN_EMAIL/"
                "FIRST_ADMIN_PASSWORD in .env don't match what's actually "
                "stored (for example after editing .env without running "
                "`docker compose down -v`), that mismatch — not this code — "
                "is why login fails.",
                existing_count,
            )
            return
        admin = User(
            email=settings.FIRST_ADMIN_EMAIL,
            full_name="Admin",
            hashed_password=hash_password(settings.FIRST_ADMIN_PASSWORD),
            role=UserRole.ADMIN,
        )
        db.add(admin)
        db.commit()
        logger.info("First admin created: %s", settings.FIRST_ADMIN_EMAIL)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_first_admin()
    yield


app = FastAPI(title=settings.PROJECT_NAME, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(companies.router, prefix=API_PREFIX)
app.include_router(contacts.router, prefix=API_PREFIX)
