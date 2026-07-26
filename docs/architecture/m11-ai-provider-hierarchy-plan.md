# AI Provider Hierarchy (Local → Free → Premium) — Architecture + Implementation Plan

Status: analysis complete, grounded in the actual current files (not the
prior review's summary — re-read directly this pass: `router.py`,
`providers/base.py`, `providers/registry.py`, `request.py`, `errors.py`,
`accounting.py`, `client.py`, `runtime.py`, `llm_engine.py`,
`core/config.py`). No implementation yet below Section 5.

## 1. Where this integrates — exact files, exact change points

The good news first: your entire spec maps onto **five additive change
points** in code that already exists for almost this exact purpose. This
is not a rebuild.

1. **`router.py`** — `RoutingDecision` already has `chain()`, an ordered
   attempt list `AIGateway.complete()` already walks, retrying/falling
   through on `retryable`/`fallback_eligible` errors. This is already
   90% of "try Local, then Free, then stop." It needs one new field
   (a `premium` list, attempted separately, only on explicit approval)
   and a policy layer that builds the right list per `AI_MODE`.
2. **`providers/registry.py`** — direct-import dict, `provider_key →
   class`. Adding Local/Free entries is exactly the same shape as the
   three that already exist.
3. **`errors.py`** — one new error type, `PremiumApprovalRequiredError`,
   alongside the existing seven.
4. **`accounting.py`** — needs one new function, a *pre-call* cost
   estimate (today's `estimate_cost_usd()` needs real token counts,
   which only exist after a call — approval needs an estimate before).
5. **`runtime.py`** — one narrow, additive `except` clause in
   `AgentRuntime.run_with_metadata()` (detailed in Section 4.4), plus
   one new optional field on `AgentExecutionResult`.

Nothing above the Gateway (`Agent`, `PromptBuilder`, `AgentRuntime`'s own
public contract) changes shape. This *is* what "the business logic must
never know which provider handled the request" already looks like in
this codebase — I'm extending the mechanism, not replacing it.

## 2. Existing Claude coupling — precise, current

Re-confirmed directly this pass, not just from the last review:

- `router.py:47-49` — `ROUTING_POLICY = {"default": RoutingDecision(primary="claude")}`.
  One line. Trivial to change.
- `providers/registry.py:31-35` — `PROVIDER_CLIENT_REGISTRY` already
  lists three providers, all real. Not Claude-only at the client layer —
  only the *routing table* is Claude-only.
- `client.py`, `errors.py`, `request.py` — zero Claude-specific logic.
  Fully generic today. This is the part of the "provider-neutral"
  requirement that's already done.
- `llm_engine.py` (Research's only real caller) — has no provider
  awareness at all; it calls `AgentRuntime.run_with_metadata()` and
  reads `execution_result.model`/`.provider_key` for observability only.
  Zero changes needed here for Local/Free routing to work — it inherits
  whatever `ROUTING_POLICY` resolves to automatically. It DOES need one
  small addition for the approval flow (Section 4.4).

Net: coupling is 100% in one dict entry plus the absence of a policy
layer above it. Nothing structural to undo.

## 3. Challenging three parts of the spec as given

You asked me not to agree by default. Three things below need a decision
from you before I implement, because "as specified" would either quietly
break the one existing AI feature, or ships something I don't think is
buildable as literally worded yet.

### 3.1 "Local AI is ALWAYS the default" vs. "never silently spend" — these interact, and the interaction is dangerous if I do it naively

The one AI feature that exists today (`RESEARCH_ANALYSIS_ENGINE_BACKEND=llm`)
currently calls Claude directly, successfully, for any operator who has
set `ANTHROPIC_API_KEY`. If I make `claude` a `premium`-tier provider and
default `AI_MODE` to Hybrid Recommended, and that operator has **not**
also configured a local or free provider (true for every existing
deployment — no local/free provider exists yet at all), the very next
research run would stop completing automatically and instead demand an
approval click that has nowhere to go yet, because Task #189 (the
approval UI) isn't built. **That would break existing functionality**,
which you told me not to do.

My resolution: ship the full tiering/routing/policy mechanism now, but
gate the actual "STOP and ask" *enforcement* behind its own dedicated
flag, `AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL`, defaulting to `False`. With
it `False` (today's state), a premium-tier provider is attempted
automatically when it's the only configured option in the chain — i.e.
byte-for-byte today's behavior. Once the approval UI exists and you
flip it to `True`, the exact same routing/tiering logic starts enforcing
the stop-and-ask gate, with zero code changes needed at that point. This
is the same "additive flag, defaults to unchanged behavior" discipline
already used for `RESEARCH_ANALYSIS_ENGINE_BACKEND` itself.

### 3.2 Mode 3 ("Automatic Premium") directly contradicts the blanket "NEVER automatically call Claude/OpenAI" rule

Both are in your spec. My reading — and the one I'll implement unless
you say otherwise — is that the blanket NEVER is the *default-mode*
rule, and Mode 3 is the named, explicit override of it, scoped to
whoever controls that setting. Today there is no per-workspace admin
role yet (you've flagged multi-user as future work), so for this phase
"the administrator enabled it" means "whoever sets `AI_MODE` in this
deployment's configuration" — a global flag, not a per-workspace one.
Per-workspace admin control over this is real future work (Section 3.3),
not implemented in this phase.

### 3.3 Per-workspace settings persistence is a schema change, and "multi-business, future multi-user" isn't built yet

Your own settings list (`AI Mode`, `Local Provider`, budget, etc., "every
workspace should eventually be able to configure") implies a new table
keyed by whatever your tenant/workspace unit ends up being. That unit
doesn't fully exist as a first-class concept yet in this codebase (I
checked — `CompanyProfile` is the closest thing to a tenant boundary
today, and there's no workspace/admin-role model). Building persisted,
per-workspace AI settings now means guessing at a data model that a
not-yet-built multi-user/workspace milestone might reshape anyway.

**Recommendation:** implement everything as a **global** setting this
phase (env var / `settings.AI_MODE`, exactly like every other AI setting
in this codebase today), architected so a later per-workspace override
is a strict *addition* (a lookup that checks a workspace row first, falls
back to the global default) — never a rewrite. I will flag in code
exactly where that future lookup slots in. Building the real
per-workspace table is better scoped as its own milestone once the
workspace/multi-user model itself is being designed, not smuggled in as
a side effect of this one.

## 4. Proposed design

### 4.1 Provider tiers are data, not code

```
PROVIDER_TIER_REGISTRY: dict[str, Literal["local", "free", "premium"]] = {
    "local_ollama": "local",
    "groq_free":    "free",
    "gemini_free":  "free",
    "claude":       "premium",
    "openai":       "premium",
    "gemini_paid":  "premium",
}
```

A provider's tier is which bucket an operator puts its `provider_key` in
— never a property the client class itself claims. This directly answers
your "don't hardcode for Gemini/Groq specifically" instruction: Gemini
can be registered as `free` (AI Studio key) or `premium` (paid key)
purely by which dict entry an operator adds; the code never special-cases
the string `"gemini"`.

### 4.2 Local and "generic free cloud" need almost no new SDK code

This is the biggest simplification I found this pass. Ollama, and Groq,
both implement the OpenAI chat-completions wire format. The `openai`
package (already a pinned dependency — no new third-party dependency
needed) supports a custom `base_url`. So:

- `OpenAICompatibleProviderClient` (new base class) — 90% shared logic
  with the existing `OpenAIProviderClient`, parameterized by
  `base_url`/`api_key`/`default_model`.
- `LocalOllamaProviderClient(OpenAICompatibleProviderClient)` — reads
  `LOCAL_MODEL_BASE_URL`/`LOCAL_MODEL_API_KEY` (optional — most local
  servers need none)/`LOCAL_MODEL_DEFAULT_MODEL`. `is_configured()` is
  true whenever `LOCAL_MODEL_BASE_URL` is set (no API key required).
- `GroqProviderClient(OpenAICompatibleProviderClient)` — reads
  `GROQ_API_KEY`/`GROQ_DEFAULT_MODEL`, `base_url` hardcoded to Groq's
  documented OpenAI-compatible endpoint.
- Gemini free vs. paid reuses the **existing** `GeminiProviderClient`
  unchanged — registered under two `provider_key`s if an operator wants
  to run both a free and a paid Gemini tier, or one, however they
  configure `PROVIDER_TIER_REGISTRY`.

This means "generic Free Cloud Provider abstraction" is a real,
literal abstraction (one class, `OpenAICompatibleProviderClient`), not
a stretch of the word.

### 4.3 Routing = capability preference list, partitioned by tier and `AI_MODE`

```
CAPABILITY_PROVIDER_PREFERENCE: dict[str, list[str]] = {
    "default": ["local_ollama", "groq_free", "gemini_free", "claude"],
}
```

`ProviderRouter.select()` becomes: look up the capability's preference
list (falling back to `"default"`, unchanged convention), partition it
by `PROVIDER_TIER_REGISTRY` into `local_and_free` / `premium`, then shape
the two lists per `settings.AI_MODE`:

- `local_only` → chain = local entries only, premium = [] (never escalate)
- `hybrid_recommended` (**default**) → chain = local + free entries,
  premium = premium entries (attempted only on approval, or
  automatically if `AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL=False` — see 3.1)
- `automatic_premium` → chain = local + free + premium, all auto-attempted
- `premium_only` → chain = premium entries only, skip local/free entirely

`AIGateway.complete()` gains: after `decision.chain()` is exhausted, if
`decision.premium` is non-empty and the request wasn't marked
`premium_approved=True` and `AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL` is
`True`, raise `PremiumApprovalRequiredError` (carrying a pre-call cost
estimate and the confidence-system's reasons — Section 4.4) instead of
attempting the premium chain. Otherwise it proceeds exactly like today's
`chain()` walk, just over a longer, tier-aware list. `GatewayRequest`
gains one new field, `premium_approved: bool = False` — default
preserves every existing caller's behavior untouched.

### 4.4 Confidence system + the approval signal, and the one required `runtime.py` change

`app/ai_gateway/confidence.py` (new, pure, no `settings` import — fully
testable in this sandbox): `assess_complexity(*, context_char_length,
document_count, response_format, reasoning_depth_hint="shallow") →
ConfidenceAssessment(score, reasons: list[str])`. Heuristic, not
learned — I want to be upfront that "confidence" here means a small set
of legible if/then rules (context length thresholds, doc count,
"structured JSON output requested" being harder for weaker models), not
a trained classifier. That's the right scope for v1; a learned version
is real future work once you have real quality data across providers
(this is exactly Migration Plan v2's Phase 3 evaluation harness from the
last review — the two plans converge here).

`PremiumApprovalRequiredError(GatewayError)` — `retryable=False`,
`fallback_eligible=False`, carries `estimated_cost_usd: float | None`,
`reasons: list[str]`, `candidate_provider_key: str`.

The one necessary change to existing code: `AgentRuntime.run_with_metadata()`
today catches bare `except GatewayError` and turns *everything* into a
generic `FAILURE`. Left alone, that would swallow the approval signal
into an indistinguishable "AI analysis failed" message — losing the
cost estimate and reasons, and giving the frontend nothing to build a
Yes/No dialog from. I'll add one narrower `except
PremiumApprovalRequiredError` clause *before* the general one, populating
a new optional field on `AgentExecutionResult`
(`premium_approval: PremiumApprovalContext | None = None`, default
`None` — every existing caller/test unaffected). `LLMAnalysisEngine.analyze()`
gets one new branch checking that field before its existing
success/failure branches. This is the smallest change that makes the
signal usable; without it, the approval feature would silently degrade
into a dead end.

### 4.5 Cost estimation, pre-call

`accounting.py` gets `estimate_pre_call_cost_usd(*, provider_key, model,
prompt_char_length, expected_completion_tokens)` — a rough
chars-per-token heuristic (≈4 chars/token, disclosed as approximate in
the docstring) times the existing price table. Returns `None` for an
unpriced model, same convention as today's post-call estimate. This is
also where Phase 1 of the earlier Migration Plan v2 (populate the price
table, wire `token_usage`/`api_cost` into `AIAnalysis`) gets done — it
was already identified as a gap independent of this spec, and this work
touches the exact same file.

### 4.6 Logging

`app/ai_gateway/request_log.py` (new) — a plain dataclass +
`log_ai_request()` that structured-logs (provider, model, capability,
tier, duration_ms, tokens, cost, success, confidence_score) via the
existing `logging` module, same as every other observability point in
this file already does. **Not a new DB table this phase** — mirrors
`accounting.py`'s own stated reasoning ("no cost dashboard exists yet");
persisting this into a queryable table is a clean, later addition once
you actually want an analytics view, not a blocker to shipping the
routing/policy mechanism itself.

## 5. Phased implementation

**Phase 1 (this pass, pending your go-ahead below):** everything in
Section 4 — tier registry, `OpenAICompatibleProviderClient` +
Local/Groq clients, tier-aware `ProviderRouter`, `AI_MODE` setting (4
modes), confidence module, `PremiumApprovalRequiredError` +
pre-call cost estimate, structured logging, the narrow `runtime.py`
addition. `AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL` defaults `False` —
**zero behavior change for any existing deployment** until you turn it
on. Fully additive, no schema migration, testable in this sandbox
wherever it doesn't touch `settings`/SQLAlchemy (same disclosed
boundary as every prior phase).

**Phase 2 (separate, later):** the actual approval UI (Task #189) —
research page shows the Yes/No dialog with cost/reasons when
`PremiumApprovalRequiredError` surfaces; only then does it make sense to
flip `AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL=True` anywhere.

**Phase 3 (separate, later):** per-workspace settings persistence
(Section 3.3) — real schema design, once the workspace/multi-user model
itself exists.

**Phase 4 (separate, later):** the learned/measured confidence system
and cross-provider evaluation harness (converges with the prior review's
own Migration Plan v2 Phase 3).

## 6. Open decision before I start writing code

Proceeding with Phase 1 exactly as scoped above — foundational,
fully additive, approval-gate off by default, no schema change, no new
third-party dependency. Sections 3.1–3.3 are the substantive
judgment calls; flagging them here rather than silently picking for you.
