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

## 6. ProviderCapabilities abstraction (CEO follow-up — added before this milestone finalizes)

Requested addition: each provider should declare capabilities
(`structured_output`, `tool_calling`, `streaming`, `vision`, `embeddings`,
`max_context_tokens`, `max_output_tokens`, `reasoning_support`), and the
Gateway should route/validate against those declared capabilities instead
of ever branching on a provider's name.

Honest starting note: there is no `if provider_key == "claude"`-style
branching anywhere in this codebase today (confirmed via
`grep -rn 'provider_key ==\|== "claude"\|== "openai"\|== "gemini"' app/` —
the only matches are in the unrelated email-provider-connections domain).
This abstraction is genuinely preventive — closing off a failure mode
before a sixth or seventh provider tempts someone into writing that
branch — not a fix for an existing violation. Worth stating plainly
rather than implying a bug that isn't there.

### 6.1 What already implicitly encodes some of this

`GatewayRequest` already carries three fields that are really capability
*requirements* in disguise: `response_format.type == JSON` (wants
`structured_output`), `tools` (wants `tool_calling`), `stream` (wants
`streaming`, though `AIGateway.stream()` itself raises
`NotImplementedError` today regardless of provider — see 6.4). Today
nothing checks whether the routed-to provider can actually satisfy these
before attempting the call; each `ProviderClient.complete()` just tries,
and either succeeds or raises `InvalidRequestError`/`InvalidResponseError`
after a real network round-trip. `vision`, `embeddings`,
`max_context_tokens`, `max_output_tokens`, and `reasoning_support` have no
corresponding request-side concept at all yet — `messages` is
text-only `list[dict]` (no image content shape exists), there is no
embeddings call path (`GatewayResponse` is chat-completion-shaped, not
embedding-vector-shaped), and nothing validates a request's size/length
against any real model ceiling before sending it.

### 6.2 Proposed shape

```python
# app/ai_gateway/capabilities.py
@dataclass(frozen=True)
class ProviderCapabilities:
    structured_output: bool = False
    tool_calling: bool = False
    streaming: bool = False
    vision: bool = False
    embeddings: bool = False
    max_context_tokens: int | None = None
    max_output_tokens: int | None = None
    reasoning_support: bool = False
```

Missing/unknown defaults to the conservative direction (`False`/`None`) —
same "fail safe, not fail permissive" precedent `tiers.tier_of()` already
established for an unclassified provider defaulting to `PREMIUM`. A
provider that hasn't declared a capability is treated as NOT having it,
never assumed capable.

### 6.3 Open question: per-provider or per-(provider, model)?

This is the one place a straight copy of `tiers.py`'s pattern would be
wrong, and worth flagging rather than silently deciding. `tiers.py`'s own
docstring is explicit that tier is a *deployment/reservation* decision,
not a property of the class — the same `GeminiProviderClient` class can
legitimately be free or premium depending on which key an operator plugs
in. Capabilities are different: `tool_calling`/`structured_output` are
real, fixed facts about what a given wire protocol/SDK integration
supports — provider-level is the right granularity for those, and a
`capabilities: ClassVar[ProviderCapabilities]` declared directly on each
concrete `ProviderClient` (same pattern `key: ClassVar[str]` already
uses) is the natural home.

But `max_context_tokens`/`max_output_tokens` (and arguably
`reasoning_support` — e.g. only some models in a given provider's lineup
have an extended-thinking mode) genuinely vary **per model**, not per
provider: `settings.ANTHROPIC_DEFAULT_MODEL` could be configured to a
model with a very different context window than another Claude model,
and a single provider-level number would be wrong for whichever one
isn't configured. `accounting.py` already solved exactly this granularity
problem for pricing — it keys `_PRICE_TABLE_USD_PER_1K` by `(provider_key,
model)`, not by `provider_key` alone. My recommendation: reuse that
precedent — provider-level `ClassVar` capabilities for the three
protocol-level booleans (`structured_output`, `tool_calling`,
`streaming`), plus a `(provider_key, model) -> partial ProviderCapabilities`
override table (mirroring the price table's own shape) for the
model-varying fields, falling back to a documented conservative default
when no specific model entry exists. This needs your sign-off before I
build it — it's more moving parts than a single flat dict, and I don't
want to build the more complex version without you confirming the
precision is worth it.

### 6.4 How the Gateway would actually use this

- **Routing**: `ProviderRouter.select()` gains a capability-filter step —
  before partitioning a capability's preference list by tier, drop any
  `provider_key` whose declared capabilities don't satisfy what the
  `GatewayRequest` actually needs (derived from `response_format`/`tools`/
  future vision-or-embeddings fields), so an incapable provider is never
  in the chain at all — not attempted, not logged as a failed attempt.
  Recomputed fresh per request (same as today), so no caching/staleness
  concern.
- **Validation / failure mode**: if filtering empties the chain AND the
  premium list entirely (every configured provider lacks the required
  capability), that's a fundamentally different failure than "nothing was
  configured" — recommend a new, distinct error
  (`NoCapableProviderError(GatewayError)`, not retryable, not
  fallback-eligible) rather than folding it into the existing generic
  "no provider chain resolved" message, so a caller/log line can tell
  "you don't have an API key set" apart from "none of your configured
  providers can do tool-calling." Open question: agree with a distinct
  error type, or fold it into the existing `GatewayError` message string?
- **`reasoning_support` specifically**: this is the one capability with no
  corresponding request field today — `confidence.py`'s
  `reasoning_depth_hint` is a parameter passed ad hoc to
  `assess_complexity()` by individual callers (`client.py`,
  `ai_preflight.py`), never threaded onto `GatewayRequest` itself, so
  there's currently nothing for the Router to read at routing time. Making
  `reasoning_support` a real routing input (not just descriptive
  metadata) means adding a new `GatewayRequest.requires_deep_reasoning:
  bool = False` field, set by `ExecutionPolicy`/`PromptBuilder`, that
  `ProviderRouter.select()` reads to exclude non-reasoning-capable
  providers from the chain when `True`. Open question: build this now
  (real behavior change, however small and additive), or declare
  `reasoning_support` on each provider as descriptive-only metadata for
  now (visible, not yet load-bearing) until a real caller needs
  deep-reasoning-aware routing?
- **`streaming` specifically**: `AIGateway.stream()` raises
  `NotImplementedError` unconditionally today, regardless of provider.
  Declaring `streaming=True` for any provider right now would describe a
  capability the Gateway itself cannot yet deliver — recommend every
  provider declares `streaming=False` until `stream()` is actually
  implemented, then flip declarations at that point, rather than
  declaring the SDK-level truth now and having it silently mean nothing.
- **`vision`/`embeddings` specifically**: neither has anywhere to be used
  via `AIGateway.complete()` today — `messages` has no image-content
  shape, and embeddings aren't a chat-completion call at all (different
  response shape entirely: a vector, not text/tool-calls). These two
  fields would be declared and correct, but inert — visible, honest
  metadata for a future milestone, not something this pass makes
  functional. Confirming that's the intent (declare now, wire up later)
  rather than scope-creeping this pass into building vision/embeddings
  request support.

### 6.5 Provisional per-provider declarations (protocol-level, pending confirmation)

Based on what each client's `complete()` already actually does today:

| provider_key | structured_output | tool_calling | streaming | reasoning_support |
|---|---|---|---|---|
| `claude` | True (prompt-instruction + parse workaround, not native JSON mode — see `claude_client.py`'s own docstring) | True | False (see 6.4) | True (model-dependent — see 6.3's per-model question) |
| `openai` | True (native `response_format`) | True | False | model-dependent |
| `gemini` / `gemini_ai_studio` (post M-AIGW-3) | True (native `response_schema`) | True | False | model-dependent |
| `local_ollama` | True (best-effort — not every local model actually honors it, see `openai_compatible_client.py`'s own disclosed caveat) | True | False | model-dependent, usually False for small local models |
| `groq` | True (best-effort, same OpenAI-compatible caveat) | True | False | model-dependent |

`max_context_tokens`/`max_output_tokens`/`vision`/`embeddings` are left
out of this table deliberately — see 6.3, these need the
per-(provider, model) design resolved first, and I don't want to publish
placeholder numbers that look authoritative but aren't sourced from a
real model card.

Awaiting your answers to 6.3 (granularity) and the two open questions in
6.4 (distinct error type, `reasoning_support` as live routing input vs.
descriptive-only) before this becomes part of M-AIGW-1's scope.

## 7. ProviderCapabilities decisions — resolved

- **Granularity (6.3): provider + per-model override table.** Protocol-level
  booleans (`structured_output`, `tool_calling`, `streaming`) stay a
  `ClassVar[ProviderCapabilities]` on each `ProviderClient`. A new
  `(provider_key, model) -> partial capability overrides` table (mirroring
  `accounting.py`'s `_PRICE_TABLE_USD_PER_1K` keying exactly) supplies
  `max_context_tokens`/`max_output_tokens`/`reasoning_support` per the
  actually-configured model, falling back to the provider-level default
  when no model-specific entry exists.
- **Failure mode (6.4): distinct `NoCapableProviderError(GatewayError)`.**
  Not retryable, not fallback-eligible — raised when capability-filtering
  empties both the chain and the premium list, kept separate from "no
  provider chain resolved" (unconfigured) so logs/callers can tell the two
  failure classes apart.
- **`reasoning_support` (6.4): real routing input now.** New
  `GatewayRequest.requires_deep_reasoning: bool = False` field
  (default preserves every existing caller), set by
  `ExecutionPolicy`/`PromptBuilder`, read by `ProviderRouter.select()` to
  exclude non-reasoning-capable providers from the chain when `True`.
  Fully additive — no existing caller sets this yet, so no behavior
  changes for Research until `ResearchAnalysisAgent`'s own
  `ExecutionPolicy` is deliberately updated to set it.
- **`vision`/`embeddings` (6.4): declare now, wire up later.** Both fields
  ship in `ProviderCapabilities` for completeness, correctly declared per
  provider, but stay functionally inert this pass — no request/response
  shape work for either is in scope here.

This is now folded into M-AIGW-1's scope (task #198, updated below) — the
plan is finalized pending your go-ahead to begin implementation.

## 8. M-AIGW-1 — approved, shipped (commit `68c0416`)

Implemented exactly as scoped: `ProviderCapabilities` (provider-level
`ClassVar` for the three protocol-level booleans + a `(provider_key,
model)` override table for `max_context_tokens`/`max_output_tokens`/
`reasoning_support`), `ProviderRouter.select()` capability-filtering,
`NoCapableProviderError`, `GatewayRequest.document_count`/
`requires_deep_reasoning`, `AIGateway.preflight()`, and
`app/research/ai_preflight.py`'s rewrite as a thin Gateway caller. Full
report (architecture summary, API changes, migration impact, test
results, risks) delivered in-chat; not duplicated here.

Two architectural notes raised at handoff, and the CEO's disposition on
each:

- **Per-model capability overrides currently have narrow practical
  effect** (every `ExecutionPolicy` today leaves `model=None`, so
  `requires_deep_reasoning` routing only ever reads provider-level
  declarations). **Disposition: keep the current implementation as-is.**
  Do not build explicit model-selection policies now — the per-model
  override table's real value lands once a future milestone's
  `ExecutionPolicy` starts deliberately selecting models. No action this
  pass.
- **`AIGateway.preflight()` doesn't yet distinguish "capability mismatch"
  from "needs approval"** — both currently surface as
  `approval_required=True` against whatever the (possibly
  capability-filtered) decision carries. **Disposition: do not modify
  M-AIGW-1.** Recorded here as a real, scoped future enhancement: a later
  milestone should evolve `PreflightResult` into a three-state result -
  `READY`, `APPROVAL_REQUIRED`, `NO_CAPABLE_PROVIDER` - once additional
  Gateway consumers exist and the distinction actually matters to a
  caller. Not built now; not forgotten either.

No further architectural changes to M-AIGW-1. Proceeding to M-AIGW-2
exactly as originally scoped in Section 4/5.

## 9. M-AIGW-2 — approved, shipped

Documentation-only, no runtime behavior change: the provider-registration
checklist (all five steps, including the `ProviderCapabilities`/
`default_model` requirements M-AIGW-1 introduced) added to
`app/ai_gateway/providers/registry.py`'s own docstring — the first file a
contributor opens when adding or modifying a provider. Full report
delivered in-chat; not duplicated here.

CEO's approval confirmed the documentation accurately reflects the
current architecture (direct-import registry, three registry
dictionaries plus settings configuration, `ProviderCapabilities`/
`default_model` requirements, no runtime behavior changes), and both
M-AIGW-1 architectural notes (Section 8 above) remain deferred exactly
as recorded — no change to either disposition.

No further changes required for M-AIGW-2. Proceeding to M-AIGW-3.

## 10. M-AIGW-3 — approved, shipped (Gemini Free-Tier Split)

Implemented exactly as scoped: `app/ai_gateway/providers/gemini_client.py`
split into a shared `_GeminiProviderClientBase` (unchanged translation
logic — the SDK integration, error mapping, and Gemini-specific message
handling this file has always had) plus two thin concrete subclasses —
`GeminiProviderClient` (`key="gemini"`, reads `GOOGLE_API_KEY`/
`GOOGLE_DEFAULT_MODEL`, unchanged from before this split) and
`GeminiAIStudioProviderClient` (`key="gemini_ai_studio"`, new, reads the
new `GOOGLE_AI_STUDIO_API_KEY`/`GOOGLE_AI_STUDIO_DEFAULT_MODEL` settings).
Both declare the same `ProviderCapabilities` — capability is a fact about
the shared SDK integration, never about which tier an operator
classifies a given key under (`tiers.py`'s own docstring).

Registered in all the places the M-AIGW-2 checklist calls out:
`PROVIDER_CLIENT_REGISTRY` (registry.py), `PROVIDER_TIER_REGISTRY` —
`gemini_ai_studio` classified FREE, `gemini` stays PREMIUM, unchanged
(tiers.py) — and `CAPABILITY_PROVIDER_PREFERENCE["default"]`, which
gained `gemini_ai_studio` (ordered after `groq`, before `claude`) but
deliberately did **not** gain `gemini` — see below.

**Disclosed pre-existing gap, not fixed in this pass:** `gemini` (the
paid key) was registered and tiered PREMIUM since M11 shipped, but was
never actually present in any `CAPABILITY_PROVIDER_PREFERENCE` entry —
meaning a deployment with `GOOGLE_API_KEY` configured has never had it
auto-attempted or gated behind approval by default routing; it's been
silently unreachable via the default capability path this whole time.
Adding `gemini_ai_studio` to the preference list is safe (a brand-new,
certainly-unconfigured setting for every existing deployment). Adding
plain `gemini` now would be a real, newly-activated behavior change for
any deployment that already has `GOOGLE_API_KEY` set — outside this
milestone's backward-compatibility mandate. Left as a disclosed, scoped
follow-up (candidate for a future milestone or a deliberate one-line
change, at the CEO's discretion) rather than silently bundled into
M-AIGW-3.

Full report (architecture impact, API impact, migration impact, test
results, risks) delivered in-chat; not duplicated here.

No further architectural changes to M-AIGW-3. M-AIGW-4/M-AIGW-5 remain
queued, not started without explicit go-ahead (Section 4/5).

CEO's approval on M-AIGW-3 explicitly recorded the disclosed `gemini`
preference-list gap above as "a deliberate future product decision
rather than silently changing routing behavior inside an infrastructure
milestone" — i.e. any future fix to it is a product/routing-policy call,
not something a later infrastructure milestone should quietly fold in.

## 11. M-AIGW-4 — approved, shipped (Cost Registry)

Implemented exactly as scoped against the five constraints the CEO set
before implementation:

1. **Centralized, Gateway-owned metadata.** All pricing stays in
   `app/ai_gateway/accounting.py` - the one place this codebase has ever
   kept it. No `ProviderClient` (gemini_client.py/claude_client.py/
   openai_client.py/openai_compatible_client.py) declares its own price;
   each still only calls `accounting.build_usage()`, unchanged.
2. **Not scattered into provider implementations.** Confirmed via `grep
   -rn "price\|_usd_per_1k" app/ai_gateway/providers/` returning nothing
   pricing-related outside calls to `build_usage()`.
3. **Model-aware: provider defaults with per-model overrides.**
   `accounting.py` now has two dicts instead of one:
   `_PROVIDER_DEFAULT_PRICE_USD_PER_1K` (one entry per `provider_key` -
   "whatever this provider's typical current-generation model costs") and
   `_MODEL_PRICE_OVERRIDES_USD_PER_1K` (the pre-existing exact
   `(provider_key, model)` table, checked FIRST). Mirrors
   `capabilities.py`'s own provider-level-default + per-model-override
   split exactly (see that module's updated docstring cross-references).
   `register_provider_default_price()` is the new registration function
   for the first tier; `register_price()` (renamed internally to target
   the override dict, same public signature) still handles the second.
4. **Independent from routing.** Confirmed via `grep -n "accounting"
   app/ai_gateway/router.py` returning nothing - `CAPABILITY_PROVIDER_PREFERENCE`,
   `RoutingDecision`, and the tier-partition logic never read a price.
   Cost stays purely informational (pre-call estimates for the
   premium-approval prompt, post-call actuals on `TokenUsage.cost_usd`)
   and a soft-budget-check input (`client.py`'s own `_check_soft_budget`,
   logs only, never blocks) - never a routing input. A future cost-aware
   policy engine can call `estimate_cost_usd()` directly without this
   module changing again.
5. **Backward compatible except where the registry itself is exercised.**
   No schema changed - `PreflightResult.estimated_cost_usd`,
   `PremiumApprovalRequiredError.estimated_cost_usd`, and
   `GatewayResponse.usage.cost_usd` were already `float | None` fields;
   this milestone only changes whether they're populated. The real,
   intended behavior change: `estimate_cost_usd()`/
   `estimate_pre_call_cost_usd()` now return a real number instead of
   `None` for the six provider_keys `PROVIDER_CLIENT_REGISTRY` currently
   registers (`claude`, `openai`, `gemini`, `gemini_ai_studio`, `groq`,
   `local_ollama`), whenever no per-model override matches first - this
   IS the fix for the "structurally complete but functionally inert in
   production" gap this project's own AI-layer architecture review
   recorded (register_price() had never once been called outside a test,
   so cost_usd was always None in real deployments). No other module's
   behavior changes.

Pricing sourced from each provider's own official pricing page,
web-verified at implementation time (2026-07-26) - see accounting.py's
own per-entry comments for the exact page/model each number is drawn
from (docs.claude.com, developers.openai.com/api/docs/pricing,
ai.google.dev/gemini-api/docs/pricing, groq.com/pricing). Disclosed as an
estimate, not an invoice - provider pricing changes regularly and this
table will drift, same "will always lag real provider catalogs"
limitation this module has always carried.

Tests: `TestProviderDefaultCostRegistry` (5 new pure tests) covering
every registered provider_key resolving to a real default price,
free-tier providers (`gemini_ai_studio`/`local_ollama`) estimating to
exactly $0, per-model override precedence over the provider default, and
`register_provider_default_price()` itself. One pre-existing test
(`test_unpriced_model_returns_none`, now
`test_unpriced_provider_and_model_returns_none`) was updated - it
previously asserted `provider_key="claude"` with an unregistered model
returned `None`, which no longer holds now that "claude" has a real
provider-level default; the updated test uses a genuinely
never-registered provider_key to confirm the true "nothing priced at
all" case still returns `None`. Full pure suite: 150 tests, 0 failures,
2 pre-existing unrelated skips.

No further architectural changes to M-AIGW-4. M-AIGW-5 remains queued,
not started without explicit go-ahead (Section 4/5).

## 12. M-AIGW-5 — scoped design note (Outreach as the Gateway's second consumer)

**Scoping clarification, stated up front.** "Outreach Personalization" is
ambiguous between two separately-shipped domains: `app/personalization/`
(M3, buyer-strategy synthesis - `DeterministicPersonalizationEngine`) and
`app/outreach/` (M4, channel content generation -
`EmailChannelProvider`). Per Decision 4 (Section 4/5) this milestone
targets **Outreach's email subject/body generation** - `app/outreach/`,
not `app/personalization/`. Personalization's own LLM upgrade is a
separate, not-yet-scoped future milestone.

**Why Outreach, and why this validates the Gateway rather than merely
using it.** Research's `ResearchAnalysisAgent` proved the Agent/Gateway
stack end to end, but with one shape of problem: a single combined call
producing four fixed, always-present JSON sections. Outreach's email
generation is structurally different in exactly the ways that matter for
proving the abstraction generalizes: (1) its output is a *variable-length
list of blocks* (one per `OutreachPlaybook` block, per-prospect), not a
fixed set of keys; (2) each block carries a `behavior`
(FIXED/AI_ASSISTED/AI_GENERATED) that determines whether the model should
touch it AT ALL - FIXED content (legal disclaimers, unsubscribe links)
must stay 100% deterministic even when the LLM backend is selected,
never rewritten by a model; (3) it is the second-ever caller of the
premium-approval/preflight machinery, the first opportunity to confirm
that machinery isn't accidentally Research-specific. If the Gateway/Agent
Runtime/PromptBuilder stack handles this shape as cleanly as Research's,
that is real evidence the abstraction is genuinely provider- AND
domain-neutral, not just "worked once."

**Design - reusing the exact seam Research established, no new
infrastructure:**

- `app/outreach/channels/llm_mapping.py` (new, pure, stdlib-only) -
  `parse_agent_response_content()`/`validate_email_response()`, the exact
  same role `research/analysis/llm_mapping.py` plays, duplicated rather
  than shared (each domain owns its own pure mapping module - Research's
  own `llm_mapping.py` isn't shared with Discovery's
  `brave_search_mapping.py` either).
- `app/outreach/channels/llm_agent.py` (new, pure) - `OutreachEmailAgent`,
  a concrete `Agent` (`app.ai_agents.base`), registered exactly like
  `ResearchAnalysisAgent`: `register_agent()`/`register_prompt_template()`/
  `register_execution_policy()` at import time. `provider_capability =
  "outreach_email_generation"` - a NEW capability key with no dedicated
  `CAPABILITY_PROVIDER_PREFERENCE` entry, falling through to the
  `"default"` list by design (identical to `ResearchAnalysisAgent`'s own
  `research_analysis` key) - zero `router.py` change needed.
  `build_context()`/`interpret()` only ever see a plain dict and a
  `GatewayResponse` - no ORM types, no provider/model reachable from
  either method's signature, same structural guarantee Research's Agent
  has.
- `app/outreach/channels/llm_email_provider.py` (new) - `LLMEmailChannelProvider`,
  a second concrete `ChannelProvider` (same interface `EmailChannelProvider`
  implements). The ORM->primitives boundary: FIXED blocks are rendered
  deterministically (reusing `email_provider.py`'s own `_substitute()`/
  `_flatten_variables()` - deliberately shared, not duplicated, same
  "share implementation, keep behavior distinct" precedent M-AIGW-3 used
  for the Gemini split) and NEVER sent to the model; only
  AI_ASSISTED/AI_GENERATED blocks are asked of `OutreachEmailAgent` via
  `AgentRuntime.run_with_metadata()`. Degrades - never raises - into a
  low-confidence outcome (FIXED blocks still render correctly) on
  premium-approval-required or a genuine Gateway failure, matching
  `LLMAnalysisEngine`'s own "degrade not crash" contract exactly.
- `app/outreach/channels/base.py` - `ChannelProvider.render()`'s abstract
  signature gains three new keyword-only parameters,
  `premium_approved: bool = False`, `company_profile_id: str | None = None`,
  `user_id: str | None = None` - all defaulted, so `provider.render(context)`
  (the one existing call site, `pipeline.py`) keeps working unmodified for
  `EmailChannelProvider`, which accepts and ignores them.
- `app/outreach/channels/registry.py` - `get_channel_provider()` gains a
  small backend-selection layer for the `"email"` channel_key only (new
  `CHANNEL_BACKEND_REGISTRY: {"email": {"deterministic": EmailChannelProvider,
  "llm": LLMEmailChannelProvider}}`, selected by the new
  `settings.OUTREACH_EMAIL_CHANNEL_BACKEND` setting), mirroring
  `research/analysis/registry.py`'s `ANALYSIS_ENGINE_REGISTRY`/
  `RESEARCH_ANALYSIS_ENGINE_BACKEND` pattern exactly. Any other
  channel_key (none exist yet) resolves via the pre-existing flat
  `CHANNEL_PROVIDER_REGISTRY`, completely untouched.
- `app/outreach/pipeline.py` - `run_outreach_request()` gains one new
  optional parameter, `run_input: dict | None = None`, from which
  `premium_approved` is extracted exactly like `run_research_request()`
  already does - defaulting to `None`/`False` preserves the one existing
  call site (`OutreachExecutionAction`, untouched) byte-for-byte.
- `app/core/config.py` - `OUTREACH_EMAIL_CHANNEL_BACKEND: str = "deterministic"` -
  default stays the existing stub, matching Research Phase 3's own
  original rollout convention (default old behavior first; flipping the
  default to `"llm"` later, if ever, is a separate, explicitly
  CEO-approved follow-up commit, exactly how `RESEARCH_ANALYSIS_ENGINE_BACKEND`'s
  default was flipped only after Research's `llm` engine had already
  shipped and been reviewed).

**Deliberately out of scope this pass (disclosed, not silently
deferred), per the explicit "validate the architecture, don't expand
Outreach functionality" instruction:** no API/schema wiring for
`premium_approved` on Outreach's `/run` endpoint or an Outreach
ai-preflight endpoint (`OutreachRequestRunBody` stays the same
documented "unused placeholder" it already was - Research's own
equivalent wiring took a separate pass after its engine shipped); no new
channels; no change to `OutreachExecutionAction` (M8.15); no attempt to
replicate the deterministic engine's fine-grained per-`block_key`
AI_GENERATED behavior branching inside the LLM prompt (the LLM path asks
for all AI_ASSISTED/AI_GENERATED block content in one call, evidence-
anchored to the primary/fallback `PersonalizationStrategy` the same way
the deterministic engine is, but without hand-tuning per-block_key
prose rules - that is real Outreach product work, not Gateway
validation).

## 13. Provider-Neutral AI Gateway v1 — complete (CEO-approved)

M-AIGW-1 through M-AIGW-5 are all approved and shipped. Research and
Outreach are both real, structurally-different Gateway consumers (fixed
four-section JSON vs. a variable per-block list), proving the
abstraction generalizes rather than being research-specific - the CEO's
own stated acceptance criterion for calling v1 complete.

See `docs/architecture/ai-gateway-consumer-landscape.md` (new companion
document) for the full picture requested before scoping the next major
AI milestone: how Research, Outreach, future Personalization, future
Reply Intelligence, and future Multi-Agent orchestration (Supervisor)
each relate to the Gateway, which of those already have a
registry/config-flag seam built versus needing one from scratch, and a
recorded (not scheduled, not implemented) future roadmap note on
consolidating `ProviderCapabilities`/pricing/tier/default-model metadata
into a single `ModelMetadata` structure.

No further changes to the Gateway's own core (`AIGateway`,
`ProviderRouter`, `PromptBuilder`, `AgentRuntime`) are implied by v1's
completion. Each future domain's Gateway adoption remains its own
future milestone, scoped and approved individually.
