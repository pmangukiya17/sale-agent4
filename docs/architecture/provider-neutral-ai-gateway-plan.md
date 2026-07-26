# Provider-Neutral AI Gateway — Architectural Review + Implementation Plan

Status: review complete, grounded in a direct read of every file listed
below (not a summary of a prior review). **No code written this pass —
per explicit instruction, this is the review + plan only, awaiting CEO
approval before anything in Section 4 is implemented.**

Feature development is paused for this milestone, per the CEO's direction.
3B (signal-adjusted priority, from the M2 Phase 3 plan) remains deferred
and out of scope here.

## 0. Headline finding, stated plainly

This is not a from-scratch build. M11 (AI Provider Hierarchy) already
shipped a real, working version of most of what's being asked for:
tiered routing (local → free → premium), automatic failover across a
chain, a human-in-the-loop premium-approval gate, pre-call cost
estimation, confidence-based reasoning, and structured request logging —
all sitting behind a genuinely provider-agnostic `GatewayRequest`/
`GatewayResponse` contract that `ResearchAnalysisAgent` (the one real
caller today) never breaks.

What's missing is narrower than "become provider-neutral" — it's five
concrete gaps, all inside `app/ai_gateway/` or the one module that
reaches around it, none requiring the Research Analysis Engine itself to
change. Section 1 is the coupling inventory; Section 2 explains why each
one matters; Section 3 is the design decisions that need your input;
Section 4 is the milestone breakdown.

## 1. Coupling inventory — every place still assuming provider identity

### 1.1 `app/research/ai_preflight.py::_default_model_for()` (lines 83–92)

```python
def _default_model_for(provider_key: str) -> str:
    return {
        "claude": settings.ANTHROPIC_DEFAULT_MODEL,
        "openai": settings.OPENAI_DEFAULT_MODEL,
        "gemini": settings.GOOGLE_DEFAULT_MODEL,
    }.get(provider_key) or provider_key
```

This is the one place in the Research domain that hardcodes provider
identity. It's a `research/` module — outside `app/ai_gateway/` entirely
— branching on `"claude"`/`"openai"`/`"gemini"` strings to guess a
default model for the pre-call cost estimate. It also silently returns
the bare `provider_key` (not a real model id) for any provider not in
this dict — a new premium provider added later would produce a
meaningless "model" string for its cost estimate, not an error, so the
bug would be invisible until someone eyeballed the estimate.

### 1.2 `app/research/ai_preflight.py` reaches into four Gateway internals directly

`compute_ai_preflight()` calls `ProviderRouter.select()`,
`app.ai_gateway.providers.registry.get_provider_client(...).is_configured()`,
`app.ai_gateway.confidence.assess_complexity()`, and
`app.ai_gateway.accounting.estimate_pre_call_cost_usd()` — four separate
imports reaching past the Gateway's public surface (`AIGateway.complete()`
is the only method the Gateway currently exposes). This works today
because there's exactly one caller, but it means "will this need
approval, and what would it cost" is Research's own orchestration, not a
Gateway capability — every future caller that wants the same preflight
answer will re-derive this same four-call sequence itself, and any
Gateway-internal change (e.g. a new tier, a new confidence signal) has to
be echoed back into this file to keep working correctly.

### 1.3 Provider registration is three hand-edited dicts across three files, not a plugin system

- `app/ai_gateway/providers/registry.py::PROVIDER_CLIENT_REGISTRY` —
  `provider_key -> class`, direct import.
- `app/ai_gateway/tiers.py::PROVIDER_TIER_REGISTRY` — `provider_key ->
  local/free/premium`.
- `app/ai_gateway/router.py::CAPABILITY_PROVIDER_PREFERENCE` — `capability
  -> ordered provider_key preference list`.

Plus one new `settings.<PROVIDER>_*` block in `app/core/config.py` per
provider (API key, default model, base URL as needed).

Adding a genuinely new provider today is a four-file code change. Compare
this to `AGENT_REGISTRY`/`ACTION_REGISTRY` elsewhere in this codebase,
which use self-registration (a new Agent/Action file registers itself on
import — zero edits to the registry file itself). The Gateway's own
provider registry was deliberately built as the "direct-import, in-package"
exception to that pattern (see `registry.py`'s own docstring) — a
reasonable choice when there were three providers, all owned by this
package. Whether it should stay that way once "provider plugins" is an
explicit requirement is Decision 1 below.

### 1.4 Gemini is tiered PREMIUM only — "Gemini AI Studio" (the CEO's named Free provider) isn't actually wired as free anywhere

`PROVIDER_TIER_REGISTRY` has exactly one `"gemini"` entry, classified
`PREMIUM`. The M11 plan doc itself proposed (Section 4.1) registering
Gemini under two separate `provider_key`s — one `free`, one `premium` —
"however \[an operator\] configures `PROVIDER_TIER_REGISTRY`" — but that
was illustrative, never actually implemented: `GeminiProviderClient` is
registered once, under one key, tiered premium. There is currently no way
to run a Gemini AI Studio (free-tier) key as FREE without either (a)
reclassifying the single `"gemini"` entry to FREE — which would also
reclassify a paid Gemini key as free, which is wrong — or (b) duplicating
the client under a second `provider_key` (e.g. `gemini_ai_studio`), which
is real, un-shipped work.

### 1.5 Cost estimation is structurally complete but functionally inert in production

`accounting.py`'s `_PRICE_TABLE_USD_PER_1K` starts empty, and
`register_price()` — the only way to populate it — is called nowhere in
production code, only in `tests/test_ai_provider_hierarchy_pure.py`.
Confirmed via `grep -rn "register_price(" backend/`: two matches, both
test/definition. Consequence: every real `GatewayResponse.usage.cost_usd`
and every `PremiumApprovalRequiredError.estimated_cost_usd` is `None`
today, in every live deployment. "Cost estimation" is a real, tested
mechanism with the data table it reads from left empty — this is a
population gap, not a design gap.

### 1.6 Confidence evaluation reads incomplete signal at its one real call site

`app/ai_gateway/client.py::_raise_premium_approval_required()` calls:

```python
assessment = assess_complexity(
    context_char_length=prompt_char_length,
    document_count=0,          # always zero, regardless of the real request
    response_format=request.response_format,
)
```

`document_count` is hardcoded to `0` — `GatewayRequest` has no field to
carry the real document count at all (confirmed: no such field in
`app/ai_gateway/request.py`), so the "Multiple data sources" reason
(`confidence.py`'s `_MULTI_DOCUMENT_THRESHOLD = 3`) can never fire from
this call site, no matter how many documents a real research run
actually has. Likewise `reasoning_depth_hint` is never passed as `"deep"`
by any production caller — it silently defaults to `"shallow"` every
time. Of `confidence.py`'s four signals, only two (`context_char_length`,
`response_format`) are ever live in production; the module is real, but
two of its four reasons are currently dead code.

`app/research/ai_preflight.py::compute_ai_preflight()` does thread a real
`document_count` through — but only for the pre-submission preflight
check, not for the actual in-flight approval raise in `client.py` above.
The two call sites disagree on how much real signal they pass.

### 1.7 Not a coupling, but worth stating precisely: what's already clean

`client.py`, `errors.py`, `request.py`, `tiers.py`, `router.py`, `runtime.py`
(`app.ai_agents.runtime`), `execution_policy.py`, `prompt_builder/builder.py`
— zero provider-specific branching. `ResearchAnalysisAgent`
(`llm_agent.py`) and `LLMAnalysisEngine` (`llm_engine.py`) never reference
a provider name; they read `execution_result.model`/`.provider_key` back
only for observability, never to change behavior. This is the part of
"provider-neutral" that was the actual hard problem, and it's already
correct.

### 1.8 The abstraction has exactly one production test case

`personalization` (M8.14), `outreach` (M8.15), CRM Automation reply
intelligence (M6.6), Mailbox Brief (Track C5), and AI Recommendations
(Track C2) are all still deterministic/rule-based — confirmed via
`grep -rl "ai_gateway\|AgentRuntime" app/` across the whole backend: none
of those five packages appear. Every claim that the Gateway is
"provider-neutral" today rests on a single real caller (Research). That
doesn't mean the abstraction is wrong — `Agent`/`PromptBuilder`/
`ExecutionPolicy` were deliberately designed generic, before Research was
the only caller — but it does mean it hasn't yet been proven against a
second capability with different response-shape needs (e.g. something
that wants tool-calling, or streaming, or a much larger/smaller context).
See Decision 4.

## 2. Why each gap actually matters (not just "should be tidier")

- **1.1 / 1.2** are the literal violation of "the Research Analysis
  Engine must never know which provider is being used" — it's the only
  place in the domain code that does. Both are fixable by giving the
  Gateway one new public method (a `preflight()` call) that internally
  does what `ai_preflight.py` does today, and by giving `ProviderClient`
  a `default_model` property so no caller ever needs a hardcoded
  provider→model dict again.
- **1.3** is the literal gap against "Provider plugins" as a named
  Gateway responsibility. This is the one item where I'd push back on
  reflexively rebuilding it as a self-registering registry — see
  Decision 1: the current direct-import registry is simple, typo-proof
  at import time (a bad `provider_key` string fails immediately, not at
  first routing attempt), and every provider today is genuinely owned by
  this package. A self-registration pattern buys "add a provider without
  touching existing files" at the cost of losing that immediacy and
  needing its own duplicate-registration guard. Worth deciding
  deliberately, not defaulting to "plugins must mean self-registration."
- **1.4** is a direct mismatch with your own stated categorization
  (Gemini AI Studio = Free). Today, turning on a Gemini key makes the
  Gateway treat it as premium — meaning it would sit behind the approval
  gate exactly like Claude/OpenAI, contradicting the free-tier framing.
- **1.5** means every cost figure in every premium-approval prompt and
  every log line is `null` right now. Nobody has approved a premium call
  today and seen a real dollar figure — the approval UI is currently
  showing "estimated cost: unknown" every time is deployed with a
  standard model.
- **1.6** means the approval prompt's "reasons" list is weaker than it
  was designed to be — a genuinely huge multi-document research run gets
  the exact same reasoning text as a two-paragraph one.
- **1.8** is a risk flag, not a defect: it means "provider-neutral" is
  currently a claim proven once, not proven in general. Worth deciding
  whether this milestone should include moving a second real capability
  onto the Gateway specifically to pressure-test the abstraction, or
  whether that's intentionally out of scope for now.

## 3. Decisions needed before I write any code

**Decision 1 — Provider registration: keep direct-import, or move to
self-registration?**
Keeping direct-import (Option A) means adding a provider is a small,
explicit, four-file diff — every provider that exists is visible in one
place. Moving to self-registration (Option B) means a new provider is a
single new file that registers its client class, tier, and (optionally)
its own settings — closer to a literal "plugin," but loses the
"everything visible in one file" property today's registry has, and
needs new guardrails (duplicate-key detection, a documented registration
order). I don't have a strong recommendation either way — this changes
how contributors add providers going forward, which is your call more
than an architecture call.

**Decision 2 — Gemini free tier: split into two provider_keys now, or defer?**
Splitting now (`gemini_ai_studio` = FREE, `gemini` = PREMIUM, both
thin wrappers around the existing `GeminiProviderClient` with distinct
settings pairs) is a small, well-scoped change and directly closes gap
1.4. Deferring it means Gemini stays premium-only until a later pass.

**Decision 3 — Cost estimation: populate the real price table now, or leave it disclosed-empty?**
Populating `accounting.py`'s table with current public per-1K-token
prices for the models actually configured (Claude/OpenAI/Gemini/Groq
defaults) is a data-entry task, not a design task — but pricing pages
change often enough that "keep this table accurate" becomes an ongoing
maintenance commitment once it's populated. Alternative: leave it
disclosed-empty (as today) and treat "no cost shown" as acceptable for
now. Your call on whether cost visibility is worth that maintenance
burden at this stage.

**Decision 4 — Prove the abstraction against a second real caller, or trust it as-is?**
Option A: as part of this milestone, migrate one more existing
deterministic feature (candidates: Outreach subject-line personalization,
or CRM Automation reply classification — both already have a
deterministic stub with a documented "swap for a real engine later" seam,
same convention `LLMAnalysisEngine` used for Research) onto the Gateway,
specifically to prove `GatewayRequest`/`ExecutionPolicy`/`ResponseFormat`
hold up for a capability with different shape needs than Research's
single-large-JSON-object pattern. Option B: treat Research as sufficient
proof and leave the other four features as future, separate milestones.
This has real scope/time cost either way, so I want your call rather than
assuming it's in scope.

## 4. Proposed milestone breakdown (implementation — not started, pending approval)

**M-AIGW-1 — Close the Research-side leaks (no behavior change, low risk)**
- Add `default_model` as an abstract property on `ProviderClient` (every
  concrete client already knows its own default-model setting — this
  just exposes it uniformly, mirroring `OpenAICompatibleProviderClient`'s
  existing `default_model` property).
- Add `AIGateway.preflight(request, *, document_count=0) -> PreflightResult`
  that internally does exactly what `ai_preflight.compute_ai_preflight()`
  does today (router select → configured check → confidence assess →
  cost estimate), reading `default_model` off the resolved
  `ProviderClient` instead of a hardcoded dict.
- Rewrite `ai_preflight.py` as a thin caller of the new Gateway method —
  Research goes from four Gateway-internal imports to one.
- Thread a real `document_count` field onto `GatewayRequest` (defaulting
  0, so every existing caller is unaffected) and have
  `client.py::_raise_premium_approval_required()` read it instead of
  hardcoding `0` — closes gap 1.6's dead signal.
- Fully additive, zero schema change, zero behavior change for any
  existing deployment — everything here is either a refactor behind an
  unchanged public contract, or a new optional field defaulting to
  today's exact behavior.

**M-AIGW-2 — Provider registration architecture (pending Decision 1)**
- If Option A (keep direct-import): document the four-file checklist
  explicitly (a short CONTRIBUTING-style note in `registry.py`'s own
  docstring) so "add a provider" has one canonical, findable procedure —
  no code change beyond documentation.
- If Option B (self-registration): design and implement a
  `register_provider_client(key, cls, tier, capability_hint=None)` entry
  point mirroring `register_agent`/`register_action`'s existing
  duplicate-guard convention, migrate the five existing providers to
  self-register, remove the three hardcoded dicts (or reduce them to the
  generated result of self-registration).

**M-AIGW-3 — Gemini free tier (pending Decision 2)**
- Register a second provider_key (`gemini_ai_studio` or similar) under
  the existing `GeminiProviderClient`, reading a distinct
  `GOOGLE_AI_STUDIO_API_KEY`/`GOOGLE_AI_STUDIO_DEFAULT_MODEL` settings
  pair, tiered FREE. Existing `"gemini"` (premium, paid key) untouched.
  Add both to `CAPABILITY_PROVIDER_PREFERENCE["default"]` in the correct
  tier order.

**M-AIGW-4 — Cost table population (pending Decision 3)**
- If populating: one `register_price()` call per (provider_key, model)
  actually in use, sourced from each provider's current public pricing
  page at implementation time, each call site disclosing the pricing
  page and date checked (same "disclosed, not silently assumed"
  discipline used throughout this codebase's AI work).

**M-AIGW-5 — Second real caller (pending Decision 4)**
- If in scope: pick one of Outreach/CRM-Automation-reply-classification,
  design its Agent/ExecutionPolicy/ResponseFormat the same way
  `ResearchAnalysisAgent` was designed, wire it in following the exact
  `LLMAnalysisEngine`-alongside-`DeterministicAnalysisEngine` pattern
  (new engine class, existing deterministic stub untouched, a settings
  flag selects between them) — this is real feature work, sized
  separately from M-AIGW-1 through 4, and would get its own approval
  gate before implementation exactly like M2 Phase 3 did.

M-AIGW-1 through 3 are small, mechanical, and low-risk — I'd recommend
doing those regardless of how Decisions 3/4 land. M-AIGW-4 and 5 are
real, separately-sized work that should get their own explicit go-ahead.

---

## 5. Decisions — resolved

CEO decisions received, recorded here before implementation begins:

- **Decision 1 (registration architecture): Option A — keep direct-import.**
  No registry restructure. M-AIGW-2 becomes documentation-only (a clear
  "how to add a provider" checklist in `registry.py`'s own docstring),
  not a self-registration rebuild.
- **Decision 2 (Gemini free tier): split into two keys now.** M-AIGW-3 is
  in scope: a new `gemini_ai_studio` provider_key (FREE tier, its own
  settings pair), existing `gemini` (PREMIUM, paid key) untouched.
- **Decision 3 (cost table): populate now.** M-AIGW-4 is in scope: real
  current per-1K-token prices for Claude/OpenAI/Gemini/Groq's configured
  default models, each `register_price()` call disclosing the pricing
  page and date checked.
- **Decision 4 (second caller): yes — migrate one now, Outreach personalization
  (M8.15).** M-AIGW-5 is in scope, targeting Outreach's subject-line/body
  personalization (currently a deterministic template engine) as the
  second real Gateway caller, following the exact
  `LLMAnalysisEngine`-alongside-`DeterministicAnalysisEngine` pattern
  Research already established (new engine class, existing deterministic
  stub untouched, a settings flag selects between them). Per this doc's
  own Section 4, M-AIGW-5 gets its own scoped architecture note (an
  Outreach-Agent-specific design pass, mirroring how
  `ResearchAnalysisAgent` was designed before M2 Phase 3's code was
  written) before its code is implemented — not skipped just because the
  overall milestone was approved.

Implementation order: M-AIGW-1 (foundation, no behavior change) →
M-AIGW-2 (documentation-only) → M-AIGW-3 (Gemini free tier) → M-AIGW-4
(cost table) → M-AIGW-5 (Outreach Agent, own design pass first).
