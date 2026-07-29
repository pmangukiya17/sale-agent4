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

    # --- M7.1: Workflow Engine ------------------------------------------------
    # Event Dispatcher worker (Part 1, Phase 4) - cheap, DB-only matching
    # work (no Action invocation happens here - see
    # event_dispatcher_worker.py's own docstring), so a short interval is
    # appropriate, matching Thread Builder's own reasoning.
    WORKFLOW_EVENT_DISPATCHER_POLL_INTERVAL_SECONDS: int = 10
    WORKFLOW_EVENT_DISPATCHER_BATCH_SIZE: int = 100

    # Step Runner worker (Part 1, Phase 5) - invokes real Actions, so
    # kept independently configurable from the dispatcher's own interval/
    # batch size, per the approved architecture's "two dedicated
    # workers, independent poll cadence" decision.
    WORKFLOW_STEP_RUNNER_POLL_INTERVAL_SECONDS: int = 10
    WORKFLOW_STEP_RUNNER_BATCH_SIZE: int = 50
    # A claimed-but-abandoned instance (worker crashed mid-step) becomes
    # reclaimable after this many minutes - same stale-claim precedent as
    # DeliveryQueueItem.SENDING.
    WORKFLOW_STEP_RUNNER_STALE_CLAIM_MINUTES: int = 10

    # --- M7.2: AI Execution Platform --------------------------------------
    # No defaults, deliberately - same "unset until configured, lazy-
    # checked at first use" pattern as CREDENTIAL_ENCRYPTION_KEY above,
    # for the same reason: a wrong default here wouldn't just silently
    # not-work, it would silently succeed with someone else's model/
    # billing assumptions. Each ProviderClient's own is_configured()
    # checks the relevant key/model pair before ever attempting a real
    # call - see app/ai_gateway/providers/base.py.
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None

    # Model IDs are NOT hardcoded anywhere in this codebase's own source -
    # provider model catalogs change too often for a code-level default to
    # stay trustworthy. Set explicitly here (or overridden per-call via
    # ExecutionPolicy.model - see app.ai_agents.execution_policy) before
    # any real Gateway call against that provider will succeed.
    ANTHROPIC_DEFAULT_MODEL: str | None = None
    OPENAI_DEFAULT_MODEL: str | None = None
    GOOGLE_DEFAULT_MODEL: str | None = None

    AI_GATEWAY_DEFAULT_TIMEOUT_SECONDS: float = 60.0
    # Attempts PER PROVIDER within one Gateway call, before falling
    # through to the next provider in the routing chain (see
    # app.ai_gateway.router.RoutingDecision.fallbacks) - independent of
    # app.workflow_engine's own, unrelated step-level max_attempts.
    AI_GATEWAY_MAX_ATTEMPTS_PER_PROVIDER: int = 2

    # Attempts for the SAME agent with the SAME AgentInput, when
    # agent.interpret() itself returns AgentOutcome.RETRY (see
    # app.ai_agents.base's own docstring) - independent of, and one
    # layer above, AI_GATEWAY_MAX_ATTEMPTS_PER_PROVIDER above (a single
    # one of these agent-level attempts may itself involve several
    # Gateway-level provider retries/fallbacks underneath it).
    AGENT_RUNTIME_MAX_ATTEMPTS: int = 2

    # --- M7.3: Supervisor / Orchestrator Layer ------------------------------
    # A hard ceiling on total steps within one Supervisor plan execution -
    # the practical, always-on guard against runaway/infinite-loop plans
    # (see app.supervisor.plan_validation's own docstring for why a
    # step-count ceiling, not true loop detection, is the right
    # pragmatic tool here - the same reasoning already applies to
    # app.workflow_engine's own per-step max_attempts). Applied uniformly
    # to every Supervisor's decisions, handwritten or LLM-driven alike.
    SUPERVISOR_MAX_EXECUTION_DEPTH: int = 50
    # Soft, same "unset until configured" precedent as
    # GatewayRequest.budget_usd - None means no plan-level cost cap is
    # enforced. Unlike the Gateway's own per-REQUEST soft check, this one
    # is a real, meaningful ceiling once set: SupervisionState.history
    # already accumulates every agent invocation's real cost_usd for the
    # life of one plan execution, so summing it needs no new persistence.
    SUPERVISOR_MAX_PLAN_COST_USD: float | None = None

    # --- M8.5: Event Backbone & Notification Center ------------------------
    # Notification worker - a pure Event CONSUMER (see
    # app/notifications/__init__.py's own docstring), cheap and DB-only
    # (no provider API call, no Action invocation), so a short interval
    # is appropriate - same reasoning as
    # WORKFLOW_EVENT_DISPATCHER_POLL_INTERVAL_SECONDS/_BATCH_SIZE above,
    # which this deliberately mirrors.
    NOTIFICATION_WORKER_POLL_INTERVAL_SECONDS: int = 10
    NOTIFICATION_WORKER_BATCH_SIZE: int = 100

    # --- M8.6: Real-Time Event Streaming ------------------------------------
    # The in-process broadcaster's own poll cadence against `events` - a
    # deliberate, approved choice to stay on the same polling operational
    # model every other background capability in this platform already
    # uses (see app/realtime/poller.py's own docstring), rather than
    # introducing Postgres LISTEN/NOTIFY as a second pattern. Short enough
    # that "server-side polling" is indistinguishable from real push at
    # human timescales, without being so tight it meaningfully loads the
    # database with many concurrent workspaces streaming at once.
    REALTIME_STREAM_POLL_INTERVAL_SECONDS: float = 1.5
    REALTIME_STREAM_POLL_BATCH_SIZE: int = 200
    # Stream tickets (app/realtime/tickets.py) are a SEPARATE, narrower
    # credential from the main access token - short-lived and scoped to
    # exactly one company_profile_id, because the browser's native
    # EventSource can't attach an Authorization header, so this one
    # connection's credential has to travel as a query parameter instead.
    # Generous relative to how long minting-to-first-connect actually
    # takes (seconds), but far shorter than ACCESS_TOKEN_EXPIRE_MINUTES -
    # if a dropped connection needs to reconnect after this window, the
    # frontend mints a fresh ticket first rather than reusing a stale one.
    REALTIME_STREAM_TICKET_EXPIRE_SECONDS: int = 300

    # --- M2 Phase 2: External Research Provider Framework ------------------
    # No default for the key itself, deliberately - same "unset until
    # configured, lazy-checked at first real use" precedent as
    # CREDENTIAL_ENCRYPTION_KEY/ANTHROPIC_API_KEY above. BraveSearchProvider.
    # health() checks this (and BRAVE_SEARCH_ENABLED below) before ever
    # attempting a real call - see app/discovery/providers/brave_search.py.
    BRAVE_SEARCH_API_KEY: str | None = None
    # A separate, explicit kill switch from "is a key present" - lets an
    # operator disable Brave Search without unsetting/losing the key (e.g.
    # a temporary pause during a billing dispute or an incident), and lets
    # the Provider Registry's iter_enabled_providers() answer "enabled or
    # not" without conflating "configured" and "turned on" into one flag.
    BRAVE_SEARCH_ENABLED: bool = True
    BRAVE_SEARCH_BASE_URL: str = "https://api.search.brave.com/res/v1/web/search"
    BRAVE_SEARCH_TIMEOUT_SECONDS: float = 10.0
    # Attempts PER QUERY VARIATION before BraveSearchProvider.search() gives
    # up and raises ProviderError for that one variation - independent of,
    # and one layer below, app.discovery.search_service.SearchService's own
    # per-variation graceful degradation (one variation exhausting its
    # retries doesn't fail every other variation for this provider - see
    # that module's own docstring). Mirrors the same
    # "attempts-per-provider-before-giving-up" shape as
    # AI_GATEWAY_MAX_ATTEMPTS_PER_PROVIDER, applied to a different layer.
    BRAVE_SEARCH_MAX_RETRIES: int = 2

    # --- M2 Phase 3: Research Intelligence Engine ---------------------------
    # Selects the active AIAnalysisEngine implementation via
    # app/research/analysis/registry.py - exact same shape/reasoning as
    # REPLY_CLASSIFIER_BACKEND above. Default was "deterministic" for the
    # initial Phase 3 commit (keyword/regex-based, no provider API calls),
    # by design, per that commit's own rollout plan step 4: "flip the
    # default in a small, separately-approved follow-up commit - not
    # bundled with the initial build." This is that follow-up: CEO
    # explicitly approved flipping the default to "llm" (the M11 AI
    # Gateway/Agent-backed engine). Still fully reversible - operators can
    # set this back to "deterministic" via env/.env - and the M11 Premium
    # Approval Gate (AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL, default True)
    # still applies unchanged: an unconfigured/no local-or-free-provider
    # deployment degrades to "AI analysis needs premium approval" outcomes,
    # never a crash and never a silent premium call. Adding a future
    # analysis backend is a new class + one registry entry + changing this
    # value, never a pipeline.py change.
    RESEARCH_ANALYSIS_ENGINE_BACKEND: str = "llm"

    # Which ChannelProvider app/outreach/channels/registry.py uses for the
    # "email" channel_key - "deterministic" (EmailChannelProvider, the
    # original M4 stub) or "llm" (LLMEmailChannelProvider, M-AIGW-5's
    # Gateway-backed provider - see
    # docs/architecture/provider-neutral-ai-gateway-plan.md Section 12).
    # Default stays "deterministic" - unlike RESEARCH_ANALYSIS_ENGINE_BACKEND
    # above (already flipped to "llm" in a separate, later, explicitly
    # CEO-approved follow-up commit after Research's engine had shipped
    # and been reviewed), this flag has not yet had that same follow-up
    # decision made for it - zero behavior change for any deployment until
    # an operator (or a future approved commit) sets it to "llm".
    OUTREACH_EMAIL_CHANNEL_BACKEND: str = "deterministic"

    # --- M11: AI Provider Hierarchy (Local -> Free -> Premium) ---------------
    # See docs/architecture/m11-ai-provider-hierarchy-plan.md for the full
    # design. AI_MODE selects which tiers app.ai_gateway.router.ProviderRouter
    # auto-attempts vs. gates behind explicit approval - a GLOBAL setting for
    # now (see that doc's Section 3.3 for why per-workspace persistence is
    # explicitly deferred, not forgotten). One of:
    #   "local_only"         - local provider(s) only, never escalate.
    #   "hybrid_recommended" - local, then free, then STOP and ask before
    #                          premium (the default).
    #   "automatic_premium"  - local, then free, then premium, all
    #                          auto-attempted - the explicit admin opt-out of
    #                          the "ask before premium" rule (spec's own Mode
    #                          3, see the design doc's Section 3.2 for how the
    #                          apparent NEVER-vs-Mode-3 contradiction resolves).
    #   "premium_only"       - premium tier only, skip local/free entirely.
    AI_MODE: str = "hybrid_recommended"

    # Whether AIGateway.complete() actually enforces the stop-and-ask gate
    # (raising PremiumApprovalRequiredError) when the local/free chain is
    # exhausted and only a premium provider remains. True from the moment
    # this ships (M11) alongside the Research page's own approval dialog -
    # see app/api/routes/research_requests.py's ai-preflight endpoint and
    # ProspectResearch.tsx's PremiumApprovalDialog. Kept as its own flag
    # (independent of AI_MODE) so it can be turned off for a deployment that
    # deliberately wants "automatic_premium"-like behavior on hybrid mode's
    # tier ordering without ever seeing the approval prompt.
    AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL: bool = True

    # M8.3 Step 7 (Premium Approval UI). The pre-authorization window
    # length: once an admin Approves a flagged capability/company via the
    # Premium Approval Center, AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL's own
    # gate above is skipped for that exact (company_profile_id, capability)
    # pair for this many minutes (see
    # app.ai_gateway.premium_approval_resolver's own docstring) - NOT a
    # resume of the specific original request (there is nothing to resume -
    # see docs/architecture/m8-3-ai-gateway-control-center-plan.md Section
    # 13's own writeup of why pause/resume was explicitly ruled out). 120
    # (CEO decision, 2026-07-29, revised up from an initial 60-minute
    # recommendation): matches the realistic "user submits, admin is
    # unavailable, admin approves later, user retries" operational cycle
    # better than a tighter window would.
    AI_GATEWAY_PREMIUM_PREAUTH_MINUTES: int = 120

    # Local inference - deliberately NOT a bespoke Ollama SDK integration.
    # Ollama, vLLM, LM Studio, and text-generation-webui all implement the
    # OpenAI chat-completions wire format, so LocalOllamaProviderClient
    # (app/ai_gateway/providers/local_client.py) is a thin subclass of
    # OpenAICompatibleProviderClient pointed at this base_url - no new
    # third-party dependency. Unset by default - is_configured() requires
    # LOCAL_MODEL_BASE_URL, same "unset until configured" precedent as every
    # other provider setting above. Most local servers need no API key.
    LOCAL_MODEL_BASE_URL: str | None = None
    LOCAL_MODEL_API_KEY: str | None = None
    LOCAL_MODEL_DEFAULT_MODEL: str | None = None
    # M8.2 addendum (approved 2026-07-28): a second locally-hosted model,
    # same server (LOCAL_MODEL_BASE_URL) - e.g. LOCAL_MODEL_DEFAULT_MODEL=
    # "qwen3:8b" (general/research/structured-JSON work) and
    # LOCAL_MODEL_SECONDARY_MODEL="llama3.1:8b" (writing/email-drafting
    # style tasks). Never read directly by LocalOllamaProviderClient or
    # any other call site - see app.ai_gateway.local_model_policy's own
    # docstring for the one place that maps a capability to a semantic
    # role ("research"/"writing"/...) and that role to whichever of these
    # two (or a future third/fourth) settings is actually configured.
    # Unset by default - if empty, LOCAL_MODEL_DEFAULT_MODEL is used for
    # every capability unchanged, same "unconfigured is normal" precedent
    # as every other optional setting in this section.
    LOCAL_MODEL_SECONDARY_MODEL: str | None = None

    # Groq - also an OpenAI-compatible endpoint (see GroqProviderClient).
    # BASE_URL has a real default since it's Groq's own fixed, documented
    # endpoint, not something an operator needs to choose - unlike
    # LOCAL_MODEL_BASE_URL, which genuinely varies per deployment.
    GROQ_API_KEY: str | None = None
    GROQ_DEFAULT_MODEL: str | None = None
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    # Gemini AI Studio - M-AIGW-3 (Gemini Free-Tier Split, see
    # docs/architecture/provider-neutral-ai-gateway-plan.md Section 7). A
    # DISTINCT key/model pair from GOOGLE_API_KEY/GOOGLE_DEFAULT_MODEL
    # above - GeminiAIStudioProviderClient (app/ai_gateway/providers/
    # gemini_client.py) reads these, tiered FREE (see
    # app.ai_gateway.tiers.PROVIDER_TIER_REGISTRY), while GOOGLE_API_KEY
    # stays the paid-tier key (tiered PREMIUM, unchanged). Both share the
    # same google-genai SDK integration (_GeminiProviderClientBase) - only
    # the credentials/tier differ, never the request/response translation
    # logic. Unset by default - zero effect on any deployment until an
    # operator obtains and sets an actual AI Studio key.
    GOOGLE_AI_STUDIO_API_KEY: str | None = None
    GOOGLE_AI_STUDIO_DEFAULT_MODEL: str | None = None

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
