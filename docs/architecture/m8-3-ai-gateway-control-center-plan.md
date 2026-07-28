# M8.3 — AI Gateway Management & Control: Architecture Review + Implementation Plan

Status: DRAFT, pre-implementation. No code written against this plan yet — per the CEO's explicit instruction, this document is the analysis/challenge/plan deliverable to review and approve before anything is built.

Scope source: the CEO's M8.3 brief (Provider Management, Model Role Management, Premium Approval Management, Live Provider Health, Routing Simulator, Provider Capability Viewer, Gateway Diagnostics).

## 1. What M8.2 actually left us with

M8.2 built a **read-only** control surface: 7 GET endpoints over live provider-registry state (`is_configured()`, declared capabilities, tier) plus one new durable table (`ai_request_logs`) for history. Nothing in the current codebase writes configuration anywhere — every provider credential, base URL, default model, retry count, and timeout is a `pydantic_settings` field read once at process boot from `.env`. `AIGateway`/`ProviderRouter`/every `ProviderClient` read `app.core.config.settings` directly; there is no indirection layer between "what's configured" and "what the code reads" for any of it.

This matters for M8.3 because **every item in the new scope is fundamentally about writing configuration that something else reads at request time** — and today, "something else" is a Python object built once at import time from environment variables. That gap is the central architectural problem M8.3 has to solve; everything else (UI, new endpoints) is comparatively mechanical.

## 2. How M8.3 integrates with the current AI Gateway

The provider-neutral design M-AIGW-1 through M-AIGW-5 and M8.2 established stays fully intact and is the right foundation:

- `ProviderRouter`/`RoutingDecision` never learn a provider's identity beyond its `provider_key` string — routing stays capability → tier/AI_MODE → capability-filter, unchanged.
- `ProviderClient` subclasses stay the only code that knows how to talk to a given vendor; `is_configured()`/`default_model`/`capabilities` stay the uniform interface everything above them reads.
- `local_model_policy.py`'s capability → role → model resolution stays the one centralized place role logic lives.
- `ui_query.py` stays the read layer; nothing in M8.3 should duplicate a query it already answers.

What M8.3 adds is a **write path** underneath that same interface: a new configuration-resolution layer that sits between `settings.<X>` and each `ProviderClient`, so a value saved through the UI is what `is_configured()`/`complete()` actually read — without breaking the "provider identity never leaks upward" rule, and without every existing `.env`-only deployment breaking on upgrade (a deployment that never touches the new UI must behave byte-for-byte as it does today, falling back to `.env`).

Concretely: `ProviderClient.is_configured()`/`default_model`/`complete()` today read `settings.<PROVIDER>_API_KEY`/`settings.<PROVIDER>_DEFAULT_MODEL` etc. directly. M8.3 needs each of those reads to instead go through one new resolution function — `resolve_provider_config(provider_key) -> ProviderConfig` — that checks a new DB-backed override table first and falls back to `settings.<X>` if no override row exists. This is a real, if mechanical, refactor across every concrete client (`claude_client.py`, `openai_client.py`, `gemini_client.py`, `groq_client.py`, `local_client.py`), not just a new table with nothing reading it.

## 3. Challenging the weaker parts of the brief

Four items in the brief either contradict an explicit, deliberate decision already on record elsewhere in this codebase, or are underspecified in a way that will blow up scope silently if left as-is. Flagging all four before writing any code, per your instruction.

### 3.1 Premium Approval "Approve/Reject" — this is the big one

`ApprovalRequestRead`'s own docstring, `ui_query.py`'s module docstring, and the M8.2 addendum doc all say the same thing, deliberately: *"this codebase's premium-approval gate is a synchronous pre-flight check ([`AIGateway.preflight()`]/[`PremiumApprovalRequiredError`]), not a durable, still-actionable request a human can act on later."* Today, when premium approval is required, the calling agent's run doesn't pause — it degrades immediately, in the same request, to a "needs approval" outcome (see `llm_engine.py`'s `PREMIUM_APPROVAL_REASONING_PREFIX`). Nothing is left waiting for a human decision. `AIRequestLog` rows tagged `PremiumApprovalRequiredError` are a historical record of "this happened," not a live queue of "this is still blocked, act on it."

A real Approve/Reject action needs one of these, and they are materially different amounts of work:

- **(a) Genuine pause/resume.** The declined run actually waits; approving it re-triggers the original request with `premium_approved=True` and the workflow continues from where it left off. This needs a new "awaiting approval" state threaded through `WorkflowInstance`/`ResearchJobStatus`/whatever else can call the Gateway, correlated back to the specific paused execution. The M11 plan doc already called this out as explicit, deferred "Phase 2" work, larger than a single milestone — building it now is a legitimate option, but it's a bigger lift than the rest of M8.3 combined.
- **(b) Pre-authorization, not resumption.** "Approve" doesn't unblock anything already run — it sets `premium_approved=True` for the *next* request of that capability/company within some validity window (e.g. "approved for the next hour"), and the original degraded run simply isn't retried automatically. Cheap to build (a new small table + one read in `AIGateway.preflight()`/`complete()`), but it changes what "Approve" means to the user in a way that needs to be surfaced honestly in the UI, not glossed over as if it resumed the original request.
- **(c) Reject is retroactive-only.** Given (a) or (b), "Reject" for a request that already completed (degraded) doesn't undo anything — it's purely an audit annotation ("this was reviewed and declined"). That's fine, but worth stating plainly rather than implying an action was stopped.

I'd recommend **(b)**, scoped honestly as pre-authorization, as the only version that fits inside M8.3 without secretly becoming a workflow-engine milestone. Recommend confirming this before I design the schema.

There's also a smaller, easy-to-miss authorization gap: this app has no RBAC (Track A's own finding, still true). Approve/Reject need *some* boundary — at minimum, restricting to the request's own company owner, matching the isolation rule `ui_query.py` already enforces for Activity/Approvals — even though full "team permissions" are correctly out of scope.

### 3.2 Semantic roles: local-only optimization, or gateway-wide model selection?

Today, `local_model_policy.py`'s role resolution is wired into exactly one place: `LocalOllamaProviderClient._resolve_model()`. Every cloud provider (`Claude`/`OpenAI`/`Gemini`/`Groq`) still just does `request.model or self.default_model` — semantic roles have zero effect on which model a premium or free-tier provider uses.

The brief asks for Coding/Vision/Embeddings/Reasoning roles alongside Research/Writing. If those roles are meant to stay a **local-tier-only** convenience (e.g. "which of my two Ollama models handles this"), the existing design generalizes cheaply — just more role entries, still only read by `local_client.py`. But if a "vision" or "reasoning" role is meant to also pick, say, a specific Claude or GPT model when the request escalates past local/free tiers (which the role names strongly imply — "reasoning" doesn't mean much for a model that's always running locally), then `_resolve_model()` needs to become a hook every `ProviderClient` implements, not just `LocalOllamaProviderClient`, and role→model resolution needs to be tier-aware (a "vision" role might resolve to a local model when local is in scope, and a cloud vision model when premium is reached). That's a bigger, more consequential change to the provider interface than "add four dict keys."

Recommend confirming scope here too: local-only roles (cheap, matches today's architecture exactly) vs. gateway-wide roles (bigger, but matches what the role names imply and is more valuable long-term).

### 3.3 "Test Connection" is new capability, not reuse — and needs a real per-provider contract

`is_configured()`'s docstring is explicit and repeated project-wide: *"never makes a network call itself."* That's a deliberate safety property every routing decision currently depends on being cheap and side-effect-free. A real Test Connection button is a genuinely new, opt-in-only, human-triggered network call — reusing the *same* `ProviderClient` instances (never a parallel HTTP client), but it's new code on every concrete client, not existing code being exposed. It also isn't one shape, though every provider's cheapest real test turns out to be the same shape: Ollama's is a `GET /v1/models` (list local models — also answers "Live Provider Health"'s "available models" requirement in the same call); Groq/OpenAI/Gemini AI Studio's cheapest real test is their own models-list endpoint, not a real completion (avoids burning real tokens/money just to check connectivity); **correction, verified via WebSearch against the pinned SDK versions before implementation**: Claude's SDK (anthropic==0.116.0) *does* expose a Models API (`client.models.list()`, GET /v1/models) — the original claim here that it didn't, and that Claude's Test Connection would therefore need a real completion call, was wrong and has been superseded. Every one of the six providers uses a models-list call for Test Connection; none needs a real completion. This needs a `test_connection()` method added to the `ProviderClient` contract with a per-provider implementation, not a generic "ping the base_url" helper.

### 3.4 Per-provider retry/timeout config touches the one shared retry loop

`AIGateway._walk()` today reads exactly one global value, `settings.AI_GATEWAY_MAX_ATTEMPTS_PER_PROVIDER`, for every provider in a chain, and a single global `AI_GATEWAY_DEFAULT_TIMEOUT_SECONDS` (which isn't even threaded into any client's actual HTTP timeout yet — worth confirming during implementation whether it's genuinely enforced anywhere today or just declared). Making these per-provider means `_walk()`'s loop needs to look up a per-`provider_key` override instead of one shared setting — a small, contained change, but a change to the Gateway's own core retry loop, which is worth calling out explicitly as touching more than "just add a settings row," even though it's low-risk.

## 4. Folder impact

```
backend/app/ai_gateway/
  provider_config.py          NEW — resolve_provider_config(), the settings-or-DB-override
                               resolution layer every ProviderClient reads through.
  diagnostics.py               NEW — pure rules module deriving warnings/recommendations
                               from existing signals (is_configured, AI_MODE, approval rate).
  routing_simulator.py         NEW — parallel to ui_query._routing_preview_for_capability(),
                               but accepts hypothetical AI_MODE/provider-enabled overrides
                               instead of reading real settings/is_configured().
  local_model_policy.py        MODIFIED — role table becomes DB-backed-with-.env-fallback,
                               same capability->role mapping stays code (rarely changes).
  providers/base.py            MODIFIED — new test_connection() contract method.
  providers/*_client.py        MODIFIED — read through provider_config.py instead of
                               settings.<X> directly; each implements test_connection().
  client.py                    MODIFIED — _walk() reads per-provider retry/timeout override.

backend/app/models/
  ai_provider_config.py         NEW — one row per provider_key (enabled, encrypted api_key,
                               base_url, default_model, retry/timeout overrides, audit cols).
  ai_model_role.py              NEW — role -> model, replaces/overlays LOCAL_MODEL_ROLES.
  ai_premium_preauthorization.py NEW — only if 3.1's option (b) is approved.

backend/alembic/versions/
  003x_ai_provider_config.py    NEW migration(s).

backend/app/schemas/ai_gateway.py   MODIFIED — write schemas (ProviderConfigWrite, etc.)
                                     alongside the existing read schemas.
backend/app/api/routes/ai_gateway.py MODIFIED — new POST/PUT/PATCH routes.

frontend/src/ai-gateway/
  hooks/useProviderConfig.ts, useModelRoles.ts, useDiagnostics.ts, useRoutingSimulator.ts  NEW
  providers/ApiGatewayProvider.ts     MODIFIED — new write methods.
  components/                        several new form/action components (provider config
                                      form, role editor, connection-test button/result).

frontend/src/pages/ai-gateway/
  AIGatewayProviderDetail.tsx    MODIFIED — becomes editable.
  AIGatewaySettings.tsx          MODIFIED — role editor replaces the read-only role table.
  AIGatewayApprovals.tsx         MODIFIED — Approve/Reject wired to real actions.
  AIGatewayHealth.tsx            MODIFIED — real connectivity/latency/available-models.
  AIGatewayRouting.tsx           MODIFIED — becomes an interactive simulator, not a fixed
                                  preview of two hardcoded capabilities.
  AIGatewayDiagnostics.tsx       NEW page + nav entry.
```

## 5. Backend impact summary

New write surface: provider enable/disable + credentials + base URL + default model + retry/timeout, model-role mapping, (if approved) premium pre-authorization. New read surface: diagnostics, routing simulation with overrides, live connection test results, available-models list. Every existing read endpoint from M8.2 stays as-is; `ui_query.py`'s functions are reused (not duplicated) by the new diagnostics/simulator modules wherever they already compute something diagnostics needs (e.g. `_is_configured_safe`, `_provider_capability_labels`).

## 6. Frontend impact summary

M8.1/M8.2's page shells, hook contract shape (`{data, isLoading, error, refresh}`), and component set (`ProviderCard`, `CapabilityMatrix`, `RoutingChainVisualizer`, `ApprovalCard`, etc.) all stay and get reused directly — `ApprovalCard`'s `onApprove`/`onReject` callbacks already exist as plain props, unwired to a backend, specifically anticipating this milestone. The real new frontend work is forms (provider config, model role editor) and one genuinely new page (Diagnostics) — not new architecture.

## 7. Database impact

Three to four new tables (provider config, model roles, optionally premium pre-authorization), all additive migrations, no changes to existing tables. `ai_request_logs` (M8.2) gets zero schema changes under option (b) in 3.1 — pre-authorization is a separate, small table, not a retrofit of the log.

## 8. API changes

All additive. New endpoints under `/ai-gateway/*`: `PUT /providers/{key}/config`, `POST /providers/{key}/test-connection`, `GET/PUT /model-roles`, `POST /routing/simulate`, `GET /diagnostics`, and (pending 3.1) `POST /approvals/{id}/approve` / `.../reject`. No existing route signature changes.

## 9. Risks

The configuration-resolution refactor (settings-or-DB-override) is the highest-risk item — it touches every provider client and needs a test proving `.env`-only deployments are byte-for-byte unaffected. Approve/Reject risks silently overpromising ("approve" that doesn't actually unblock anything) if 3.1 isn't resolved before building. Test Connection risks real (small) cost/rate-limit consumption if not clearly gated as an explicit, human-triggered action. Storing AI provider API keys in the DB is a real secret-handling responsibility — reuse the existing Fernet/`CREDENTIAL_ENCRYPTION_KEY` primitive (`app/delivery/credentials/`), don't invent a second encryption scheme.

## 10. Future scalability considerations

`resolve_provider_config()` as a single named resolution point means a future per-tenant provider config (if this app ever grows real multi-tenancy) is a filter added to one function, not a re-plumb. Model roles staying data (DB rows), not code, is what makes "future models addable without business-logic changes" (M8.2's own requirement) continue to hold. Diagnostics/simulator being pure derivations over existing signals means adding a new provider automatically shows up in both without new diagnostic-writing work.

CEO-noted future recommendations (both explicitly NOT for this milestone, recorded here so they aren't lost rather than acted on prematurely):

1. **Test Connection → real provider health check.** Today (Step 2) Test Connection is a cheap models-list call that fails fast when no credentials are configured - correct, and should remain the behavior when nothing is configured. Once credentials ARE configured, Test Connection could eventually perform a genuine lightweight health check (authentication + a minimal real API request) and report connection status, latency, and any authentication error - richer signal than "the models-list call succeeded." Deferred - no change to `ProviderClient.test_connection()`'s current contract this milestone.
2. **Custom business AI roles** (e.g. Negotiation, Price Analysis, Market Intelligence, Supplier Validation, Legal Review) - to be considered after M7/M9, not before. Model Role Management's (Step 3) `ai_model_roles` table already supports adding any new role NAME as a DB row with zero code change (see `AIModelRole`'s own docstring); what's explicitly deferred is CAPABILITY -> role preference wiring for these new business-domain roles, since each one needs its own capability defined and threaded through the relevant agent first (same "capability must exist as live Gateway traffic before its role preference is meaningful" constraint `CAPABILITY_LOCAL_MODEL_ROLE`'s own disclosed-scope note already established for `buyer_discovery`/`crm_data_extraction`). This must not change the current routing architecture - capability -> role preference stays code-level (Section 12 decision 2), same as every other role added so far.
3. **Routing Simulator (Step 4) → richer step-by-step decision trace.** Today's `RoutingSimulatorPanel` shows the full candidate chain as a flat, ordered list (one node per candidate, each with its own state/reason/cost). A future pass could present this as a genuine step-by-step visual flow - capability requirements first, then each candidate's evaluation and exclusion reason in sequence, then the final selection rationale and estimated cost - closer to a guided walkthrough than a table. Deferred: `build_simulation()`'s own pure computation already returns everything such a view would need (ordered nodes, `capability_excluded`, `requested_capabilities`, per-node `reason`/`estimated_cost_usd`); this would be a presentation-layer enhancement only, no backend change.

## 11. Implementation plan (locked scope, per Section 12 decisions)

1. `provider_config.py` resolution layer + migration (`ai_provider_configs`, encrypted API key via the existing Fernet/`CREDENTIAL_ENCRYPTION_KEY` primitive) + every `ProviderClient` refactored to read through it; prove zero behavior change for `.env`-only deployments (full existing regression suite must stay green — this is the step where a mistake would be most damaging, so it ships alone, verified, before anything else touches it).
2. Provider Management UI + endpoints: enable/disable, credentials, base URL, default model, Test Connection (new `test_connection()` on `ProviderClient`, per-provider implementation — a models-list call for every provider, including Claude; see Section 3.3's correction). Retry/timeout stay global, not part of this step.
3. Model Role Management: DB-backed role table (`ai_model_roles`) + editor UI, wired ONLY into `LocalOllamaProviderClient._resolve_model()` — Coding/Vision/Embeddings/Reasoning added as more rows, not new cloud-client logic.
4. Routing Simulator — mostly reuses existing `_routing_preview_for_capability` logic, extended to accept hypothetical AI_MODE/provider-enabled overrides instead of only reading live settings.
5. Provider Capability Viewer — near-free: add the missing `embeddings` label to `_provider_capability_labels()`, reuse `CapabilityMatrix` as-is.
6. Gateway Diagnostics — new pure rules module (`diagnostics.py`) + endpoint + page, derived entirely from existing signals (`is_configured()`, AI_MODE, approval/rejection rate from `ai_request_logs`).
7. Premium Approval Management (pre-authorization) — new small table (`ai_premium_preauthorization`), one read added to `AIGateway.preflight()`/`complete()`'s existing gate check, Approve/Reject wired in `ApprovalCard`. Built last, once the config-resolution layer (step 1) is proven stable.

## 12. Decisions (CEO-approved, 2026-07-28)

1. **Premium Approval → pre-authorization.** "Approve" sets `premium_approved`-equivalent for the next N minutes for that capability/company; it does not resume the original degraded run. "Reject" is an audit annotation. New small table (`ai_premium_preauthorization` or similar), read once in `AIGateway.preflight()`/`complete()` alongside the existing gate check. No pause/resume, no WorkflowInstance state changes.
2. **Semantic roles → local-tier only.** `local_model_policy.py`'s role resolution stays wired to `LocalOllamaProviderClient._resolve_model()` alone. Cloud provider clients are NOT touched — Coding/Vision/Embeddings/Reasoning roles are added as more entries in the same dict-shaped mapping, DB-backed per decision 3, but only ever consulted by the local client.
3. **Provider config writes → DB-backed override with `.env` fallback.** New encrypted table, reusing the existing Fernet/`CREDENTIAL_ENCRYPTION_KEY` primitive from `app/delivery/credentials/`. One new `resolve_provider_config()` function every `ProviderClient` reads through; falls back to `settings.<X>` when no override row exists, so `.env`-only deployments are unaffected.
4. **Retry/timeout → stay global for now.** No change to `AIGateway._walk()`'s single shared `AI_GATEWAY_MAX_ATTEMPTS_PER_PROVIDER`/`AI_GATEWAY_DEFAULT_TIMEOUT_SECONDS` this milestone. Provider Management ships API keys/base URL/default model/enable-per-provider only; per-provider retry/timeout is explicitly deferred.

These narrow section 3's four challenges to a locked scope — updating the plan below accordingly.
