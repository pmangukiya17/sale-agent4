import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    auth,
    brand_email_signatures,
    companies,
    company_profiles,
    contacts,
    discovery_jobs,
    discovery_runs,
    discovery_searches,
    health,
    icp_criteria,
    intelligence_snapshots,
    knowledge_base,
    outreach_drafts,
    outreach_jobs,
    outreach_playbooks,
    outreach_requests,
    outreach_runs,
    personalization_jobs,
    personalization_requests,
    personalization_runs,
    personalization_snapshots,
    personalization_templates,
    products,
    prompt_versions,
    prospect_contacts,
    prospect_timeline,
    prospects,
    recommendations,
    reference_data,
    research_jobs,
    research_reports,
    research_requests,
    research_runs,
    research_templates,
    search_templates,
    signals,
    workspace_settings,
)
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
app.include_router(company_profiles.router, prefix=API_PREFIX)
app.include_router(products.router, prefix=API_PREFIX)
app.include_router(icp_criteria.router, prefix=API_PREFIX)
app.include_router(knowledge_base.router, prefix=API_PREFIX)
app.include_router(workspace_settings.router, prefix=API_PREFIX)
app.include_router(reference_data.router, prefix=API_PREFIX)
app.include_router(search_templates.router, prefix=API_PREFIX)
app.include_router(discovery_searches.router, prefix=API_PREFIX)
app.include_router(discovery_jobs.router, prefix=API_PREFIX)
app.include_router(discovery_runs.router, prefix=API_PREFIX)
app.include_router(prospects.router, prefix=API_PREFIX)
app.include_router(prospect_contacts.router, prefix=API_PREFIX)
app.include_router(prospect_timeline.router, prefix=API_PREFIX)
app.include_router(research_templates.router, prefix=API_PREFIX)
app.include_router(research_requests.router, prefix=API_PREFIX)
app.include_router(research_jobs.router, prefix=API_PREFIX)
app.include_router(research_runs.router, prefix=API_PREFIX)
app.include_router(intelligence_snapshots.router, prefix=API_PREFIX)
app.include_router(signals.router, prefix=API_PREFIX)
app.include_router(recommendations.router, prefix=API_PREFIX)
app.include_router(research_reports.router, prefix=API_PREFIX)
app.include_router(personalization_templates.router, prefix=API_PREFIX)
app.include_router(personalization_requests.router, prefix=API_PREFIX)
app.include_router(personalization_jobs.router, prefix=API_PREFIX)
app.include_router(personalization_runs.router, prefix=API_PREFIX)
app.include_router(personalization_snapshots.router, prefix=API_PREFIX)
app.include_router(outreach_playbooks.router, prefix=API_PREFIX)
app.include_router(prompt_versions.router, prefix=API_PREFIX)
app.include_router(outreach_requests.router, prefix=API_PREFIX)
app.include_router(outreach_jobs.router, prefix=API_PREFIX)
app.include_router(outreach_runs.router, prefix=API_PREFIX)
app.include_router(outreach_drafts.router, prefix=API_PREFIX)
app.include_router(brand_email_signatures.router, prefix=API_PREFIX)
