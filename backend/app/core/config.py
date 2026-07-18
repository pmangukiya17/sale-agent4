from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Sales Agent"
    ENV: str = "development"

    # Database
    POSTGRES_USER: str = "sales_agent"
    POSTGRES_PASSWORD: str = "sales_agent"
    POSTGRES_DB: str = "sales_agent"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    # Auth
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12

    # First admin user, auto-created on startup if no users exist
    FIRST_ADMIN_EMAIL: str = "admin@shiveshwartextiles.com"
    FIRST_ADMIN_PASSWORD: str = "change-me-immediately"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- M5: Outreach Delivery Engine ---------------------------------------
    # No default, deliberately - unlike SECRET_KEY above. A leaked JWT
    # secret is bad but revocable; a leaked credential-encryption key with a
    # known default would silently decrypt every stored mailbox OAuth
    # token. PostgresFernetCredentialStore raises at first actual use (not
    # at app startup) if this is unset, so the rest of the app keeps
    # working even before Delivery is configured.
    CREDENTIAL_ENCRYPTION_KEY: str | None = None
    CREDENTIAL_STORE_BACKEND: str = "postgres_fernet"

    # Point at the FRONTEND, not the backend, deliberately - a Layer 5
    # decision, changed from Layer 3's original backend-hosted callback.
    # Google/Microsoft's redirect can never carry an Authorization header,
    # so a backend-hosted callback would have to be a public, unauthenticated
    # endpoint with no way to verify who is completing the flow. Routing
    # through the frontend lets the still-logged-in SPA complete the
    # connection via an authenticated backend call instead - see
    # connection_service.py's and app/delivery/oauth_state.py's docstrings
    # for the full reasoning (this alone is not sufficient without the
    # signed, time-bounded `state` those modules also implement). Both
    # providers share one frontend route - provider_key travels inside
    # `state`, not the URL, so there's no need for two frontend paths.
    GMAIL_OAUTH_CLIENT_ID: str | None = None
    GMAIL_OAUTH_CLIENT_SECRET: str | None = None
    GMAIL_OAUTH_REDIRECT_URI: str = "http://localhost:5173/oauth/callback"

    MICROSOFT_OAUTH_CLIENT_ID: str | None = None
    MICROSOFT_OAUTH_CLIENT_SECRET: str | None = None
    MICROSOFT_OAUTH_TENANT_ID: str = "common"
    MICROSOFT_OAUTH_REDIRECT_URI: str = "http://localhost:5173/oauth/callback"

    DELIVERY_SCHEDULING_POLICY: str = "fifo"
    DELIVERY_WORKER_POLL_INTERVAL_SECONDS: int = 15
    DELIVERY_WORKER_BATCH_SIZE: int = 10
    DELIVERY_WORKER_STALE_CLAIM_MINUTES: int = 10
    DELIVERY_DEFAULT_MAX_ATTEMPTS: int = 3

    # --- M6.2: Mailbox Synchronization --------------------------------------
    # Slower default poll than the Delivery worker's - sync is a background
    # freshness concern, not a time-sensitive send; a wider interval is
    # kinder to the provider API's rate limits for a capability nothing yet
    # depends on synchronously (M6.3+ reads EmailMessage rows whenever they
    # arrive, not "as of this exact second").
    MAILBOX_SYNC_POLL_INTERVAL_SECONDS: int = 60
    # Per-connection, per-tick cap passed as max_results/$top to
    # IncrementalSyncCapable.fetch_messages_incremental - keeps one slow
    # mailbox from starving the tick loop's time budget for every other
    # connected mailbox.
    MAILBOX_SYNC_MAX_RESULTS_PER_TICK: int = 50

    # --- M6.3: Thread Builder ------------------------------------------------
    # Faster than the mailbox sync worker's own interval on purpose - once
    # a message is sitting in the WHERE conversation_id IS NULL queue,
    # there's no reason to make it wait as long as a full sync cycle to be
    # threaded; threading is cheap (DB-only, no provider API calls).
    THREAD_BUILDER_POLL_INTERVAL_SECONDS: int = 20
    THREAD_BUILDER_BATCH_SIZE: int = 50

    # --- M6.4: Reply Intelligence --------------------------------------------
    # No batch size setting here, deliberately - unlike the other three
    # workers, Reply Intelligence does a full recompute every tick (no
    # cursor - see reply_intelligence_worker.py's own docstring), so there
    # is no ordered backlog to cap a slice of. Poll interval matches
    # Thread Builder's: cheap, DB-only work for the MVP rules classifier,
    # no provider API calls.
    REPLY_INTELLIGENCE_POLL_INTERVAL_SECONDS: int = 20
    # Selects the active ReplyClassifier implementation via
    # app/reply_intelligence/classifiers/registry.py - "rules" is the only
    # backend implemented in M6.4 (deterministic, no AI provider). Adding
    # "openai"/"claude"/"gemini"/a local-model backend later is a new
    # class + a registry entry + changing this value, never a worker change.
    REPLY_CLASSIFIER_BACKEND: str = "rules"

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
