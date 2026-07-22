import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    ai_workforce,
    auth,
    brand_email_signatures,
    companies,
    company_profiles,
    contacts,
    conversations,
    delivery_campaigns,
    delivery_onboarding,
    delivery_queue_items,
    discovery_jobs,
    discovery_runs,
    discovery_searches,
    events,
    health,
    icp_criteria,
    intelligence_snapshots,
    knowledge_base,
    notifications,
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
    provider_connections,
    realtime,
    recommendations,
    reference_data,
    research_jobs,
    research_reports,
    research_requests,
    research_runs,
    research_templates,
    search_templates,
    sending_profiles,
    signals,
    workspace_settings,
)
from app.core.config import settings
from app.core.security import hash_password
from app.db import base as _base  # noqa: F401  (imports every model so relationship() string refs resolve)
from app.db.session import SessionLocal
from app.delivery.providers.registry import PROVIDER_REGISTRY
from app.models.enums import UserRole
from app.models.user import User
from app.realtime import poller as realtime_poller
from app.supervisor.observability import install_execution_id_log_filter
from app.workflow_bootstrap import activate_builtin_workflows

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sales_agent")
# M7.3: stamps every log record process-wide with the current
# Supervisor execution id (None outside a Supervisor-driven call) - see
# app.supervisor.observability's own docstring for why this is a
# handler-level filter, not a field threaded through every request/
# response dataclass in the AI stack.
install_execution_id_log_filter()


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


def bootstrap_builtin_workflows() -> None:
    """M7.1 Part 2: activates every built-in WorkflowDefinition this
    application ships with (see app/workflow_bootstrap.py's own
    docstring for BUILTIN_WORKFLOW_DEFINITIONS - today just the
    conversation.created pilot; future M7.x/M8/M9 built-ins are added
    there, never here). Safe to run on every startup - idempotent,
    additive-only, same "no-op once already done" shape as
    ensure_first_admin() above."""
    db = SessionLocal()
    try:
        activate_builtin_workflows(db)
    finally:
        db.close()


def log_delivery_configuration_status() -> None:
    """Informational only - never raises, never blocks startup (Delivery
    is optional, per-connection functionality; see
    PostgresFernetCredentialStore._get_fernet's docstring for why
    CREDENTIAL_ENCRYPTION_KEY itself is deliberately lazy-checked at first
    use, not startup-gated, and app/main.py's is_configured() filtering on
    /delivery/providers for the same reasoning applied to OAuth). This
    just makes the current configuration state visible in the startup
    logs, since the M5 Layer 7 investigation showed the alternative is
    discovering it by clicking Connect and reading a stack trace."""
    for provider_cls in PROVIDER_REGISTRY.values():
        logger.info("Delivery: %s OAuth configured = %s", provider_cls.key, provider_cls().is_configured())
    logger.info("Delivery: CREDENTIAL_ENCRYPTION_KEY configured = %s", bool(settings.CREDENTIAL_ENCRYPTION_KEY))


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_first_admin()
    log_delivery_configuration_status()
    bootstrap_builtin_workflows()
    # M8.6: the Real-Time Event Streaming poller - the one background
    # capability in this platform that runs INSIDE the FastAPI process
    # rather than as its own docker-compose worker service, because it
    # holds this process's own live SSE connections in memory (see
    # app/realtime/__init__.py's own docstring for why that's structural,
    # not a shortcut). Started here, cancelled on shutdown, same
    # "app owns the background task's lifecycle" shape uvicorn's own
    # lifespan protocol is meant for.
    realtime_poller.start()
    yield
    await realtime_poller.stop()


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
# M8.4 backend addition: read-only AI Workforce domain API - see
# app/ai_workforce/__init__.py. Registered here (not clustered near
# discovery/research/etc.) since it isn't its own pipeline domain; it's a
# read-only view over the M7 Workflow Engine's own tables.
app.include_router(ai_workforce.router, prefix=API_PREFIX)
# M8.5 Event Backbone: the platform Event stream's read API, and the
# Notification Center that consumes it. See app/notifications/__init__.py
# for the worker that's the only thing that ever creates a Notification.
app.include_router(events.router, prefix=API_PREFIX)
app.include_router(notifications.router, prefix=API_PREFIX)
# M8.6: Real-Time Event Streaming - Server-Sent Events over the same
# `events` table, via the in-process broadcaster/poller started above in
# `lifespan`. See app/realtime/__init__.py for the package boundary and
# app/api/routes/realtime.py for why this router's two endpoints use two
# different auth mechanisms.
app.include_router(realtime.router, prefix=API_PREFIX)
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
# M5: Outreach Delivery Engine
app.include_router(sending_profiles.router, prefix=API_PREFIX)
app.include_router(provider_connections.router, prefix=API_PREFIX)
app.include_router(delivery_campaigns.router, prefix=API_PREFIX)
app.include_router(delivery_queue_items.router, prefix=API_PREFIX)
app.include_router(delivery_onboarding.router, prefix=API_PREFIX)
# M6.5: Conversations UI - read-only over the M6.1-M6.4 schema
app.include_router(conversations.router, prefix=API_PREFIX)
