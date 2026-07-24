# AI Layer Architecture Review — "Migration Plan v2"

Status: **REVIEW ONLY. No code changes in this document. Implementation is
paused pending your decision.**

Scope: a full senior-architecture review of the AI/LLM layer, ordered per
your brief — critical evaluation of the current architecture (challenging
assumptions where warranted), a coupling audit of the actual codebase, a
proposed provider-neutral architecture, and a four-phase migration plan.

## 0. Bottom line, up front

**Do not do a full redesign. Do a focused four-phase extension, and do
it now, before Personalization/Outreach/Reply Intelligence each grow
their own AI backend.**

The AI Gateway you already have (`app/ai_gateway/`, `app/ai_agents/`,
`app/prompt_builder/`) is a genuinely provider-neutral design. It routes
by *capability*, not by *provider name*; nothing above the Gateway is
allowed to know which provider served a request; an Agent's own code has
no signature path that could even reach a provider/model/temperature
value. That is the right architecture, and it is rare to get this right
on a first pass. The actual problem is narrower and more mundane than
"the architecture is coupled to Claude": **the *configuration* is
100% Claude, because there is exactly one entry in the routing table and
zero lines of code exist for talking to a local model.** That is a
data/config gap and a missing provider client, not a structural flaw.

The good news this review found, which changes the urgency calculus:
today, exactly **one** feature in the entire product (Research
Intelligence's optional, off-by-default `"llm"` engine) has ever called
the AI Gateway for real. Discovery, Personalization, Outreach, Reply
Intelligence, CRM Automation, Mailbox Brief, and Supervisor are all still
100% deterministic. The blast radius of "Claude coupling" today is one
optional feature, not the product. That is exactly why this is the right
moment to act: the next several roadmap items (Personalization, Outreach,
Reply Intelligence AI backends) are about to be built. If they're each
built against today's single-entry, cloud-only routing table, you'll be
retrofitting five call sites later instead of extending one pattern now.

Full reasoning, coupling audit, architecture proposal, and phased plan
follow.

---

## 1. What the codebase actually shows (research summary)

Full detail is in Section 3 (coupling audit); this is the headline
picture.

- **`app/ai_gateway/`** — three real, fully-implemented provider clients
  (`ClaudeProviderClient`, `OpenAIProviderClient`, `GeminiProviderClient`
  — not stubs, all call real SDKs, pinned in `requirements.txt`:
  `anthropic==0.116.0`, `openai==2.46.0`, `google-genai==2.12.1`).
  Selection is capability-based (`GatewayRequest.capability` →
  `ProviderRouter.select()` → `RoutingDecision.chain()`), never by a
  caller-supplied provider name — confirmed by grep across the entire
  codebase, with zero production call sites that hardcode a provider.
- **`ROUTING_POLICY`** (`app/ai_gateway/router.py`) has exactly one
  entry: `{"default": RoutingDecision(primary="claude")}`. Every
  capability that doesn't have its own entry — which today is *every*
  capability, including Research's own `"research_analysis"` — falls
  through to this one Claude-only chain with zero fallbacks.
- **`AGENT_REGISTRY`** has exactly one concrete Agent:
  `ResearchAnalysisAgent` (`app/research/analysis/llm_agent.py`), feeding
  `LLMAnalysisEngine`, itself one of two engines selectable via
  `RESEARCH_ANALYSIS_ENGINE_BACKEND` (default `"deterministic"`, i.e. off
  by default).
- **Every other domain is deterministic today, by design, not by
  accident**: Discovery scoring, CRM Automation's relationship-stage
  state machine, Personalization's narrative engine, Outreach's email
  templating, Reply Intelligence's rules classifier, and Mailbox Brief's
  synthesis are all explicit, documented, rule-based stubs with a
  written prohibition against a real model call "for this milestone."
  `Supervisor` has zero concrete implementations and nothing wired to a
  production trigger.
- **No local-inference dependency exists at all** — no `ollama`,
  `llama-cpp-python`, `transformers`, `torch`, no vector/embeddings
  library either. "Local models whenever practical" is 0% built today,
  not partially built.
- **Cost accounting is real in shape but empty in practice**: the price
  table starts empty and nothing populates it; `LLMAnalysisEngine`
  doesn't even copy `token_usage`/`api_cost` into the two DB columns
  that already exist for exactly this purpose. There is no per-tenant
  budget ledger anywhere, and `BudgetExceededError` is declared but
  never raised — hard budget enforcement was explicitly deferred pending
  "a per-company/per-period spend total to check against, which does not
  exist yet."

---

## 2. Answers to your eleven questions

### 1. Should Anthropic remain the primary architecture?

Reframing the question first, because "Anthropic as the architecture" is
the wrong unit of analysis. Anthropic is not woven into the
architecture — it's one line in a routing table. The real question is:
*should Claude remain the default provider for the capabilities that
currently use AI at all, while the underlying routing mechanism stays
provider-neutral?* Yes, as a pragmatic default, for now — Claude has the
working integration, the best measured structured-output reliability of
the three cloud providers already implemented here, and switching the
*default* costs one line, not a redesign. What must change is that it
stop being the *only* configured option anywhere. It should be one
interchangeable, revisitable entry, never hardcoded as "the" answer for
a capability again.

### 2. Should Ollama/local inference become the default?

Not blanket, and I'd push back on "the default" as a single global
switch. Smaller open-weight models run via Ollama are measurably weaker
at strict structured-output conformance and multi-step judgment than
Claude/GPT-class models today — untested claims aside, this is a
capability-by-capability empirical question, not an architectural
default. The right framing: local inference should become the default
**for self-hosted/privacy-sensitive deployments, and for capabilities
that are well-bounded classification/extraction tasks** — informed by
actual measurement (Phase 3 below builds exactly this measurement
mechanism), not assumed. Defaulting Research Intelligence's nuanced
sales-signal synthesis to an unverified 7B local model the day this
ships would be optimizing for the wrong thing.

### 3. Should we instead build a provider-neutral AI platform?

Yes — and you already have 90% of one. The Gateway/Router/Agent split
already refuses to let anything above it know which provider ran. What's
missing is not a redesign, it's: a local-model-compatible provider
client (doesn't exist), per-capability routing entries (only one global
entry exists), a per-tenant override layer (doesn't exist — routing is
process-global today), and a way to decide "is local good enough here"
with data instead of guessing. All four are additive to the existing
design.

### 4. Which modules actually need frontier cloud models?

The ones doing ambiguous, high-stakes, multi-step judgment over messy
text, where a wrong or shallow answer has real commercial cost:
Research Intelligence's synthesis and sales-recommendation reasoning
(once past simple keyword-style extraction), Personalization's strategy
generation (deciding *what* will actually resonate with a specific
buyer is a judgment call, not a lookup), high-quality persuasive
Outreach copywriting (a customer complaint here is either "an
embarrassing paragraph" or "we didn't get the sale"), and any future
Supervisor/multi-agent planning reasoning (deciding what an agent should
do next from ambiguous state is exactly the kind of task frontier
models are currently best at). These are the tasks worth paying
per-token for.

### 5. Which modules are perfectly suited for local models?

Bounded classification and low-stakes structured extraction, where
being right 90% of the time at near-zero marginal cost beats being right
97% of the time at real recurring cost: Reply Intelligence's
positive/negative/neutral/out-of-office classification (already a
solved, bounded problem — currently rules-based, and a small local
classifier is a more natural next step than Claude ever would be),
query-variation expansion in Discovery if that ever gets an AI layer
(low-stakes, template-like), and simple metadata tagging over short,
clean text. These are good local-model candidates specifically because
the cost of an occasional wrong answer is low and recoverable.

### 6. Which tasks should remain deterministic rather than AI-driven?

CRM Automation's relationship-stage state machine — this is an
auditable business-state transition, not a judgment call, and it was
correctly, deliberately built to avoid needing an AI pipeline at all;
that decision should stand indefinitely. Discovery's scoring math (the
`score_breakdown` factor computation) should stay deterministic for the
same reason — its explainability requirement is fundamentally in
tension with letting a model produce the number; if you want an AI
layer here later, it should *add* a narrative `ai_reasoning` on top of
the existing deterministic score (a column that already exists, sitting
null, for exactly this), not replace the scoring math itself. Anything
touching auth, billing, or workflow-engine step transitions: always
deterministic, no exceptions.

### 7. Performance, maintenance, scalability, deployment trade-offs

Cloud (Claude/OpenAI/Gemini): best quality today, zero infrastructure to
run, and the vendor's own upgrades improve your product for free. Costs:
recurring, usage-scaled — the thing you're trying to get away from —
plus data leaving customer infrastructure, which is a hard blocker for
some privacy-sensitive/self-hosted customers regardless of price.

Local inference: no recurring per-call fee, data never leaves the
customer's infrastructure, works offline. But — and this is the honest
part — **it is not free, it's a different bill.** Nothing in this
codebase talks to a local model today; building and running that well
is real engineering and real infrastructure. Every self-hosted customer
now needs GPU/CPU capacity they didn't need before. If Sales-Agent4 ever
hosts a shared local-model tier for SaaS customers, *you* now own GPU
fleet capacity planning, autoscaling, and model-version lifecycle —
meaningfully more operational surface than "call an API," and a genuine
new maintenance burden, not a savings, unless usage volume is high
enough to justify it. Open models are also far more sensitive to exact
prompt formatting and chat templates than Claude/GPT — expect real
prompt-tuning effort per model you adopt, and expect to redo some of it
when you upgrade models.

Net: local inference is the *right* default for self-hosted/enterprise
customers who already own their infrastructure and whose compliance
posture demands it. It's the *wrong* default to force onto your own
SaaS tier before you have the usage volume and ops maturity to run
shared inference well. Trying to make it the global default now would
be optimizing for a five-year-away deployment shape at the cost of
today's velocity — the opposite of what you asked me not to do.

### 8. How should AI provider selection work?

Layered, in this order: (1) **capability** — already exists, needs more
entries registered as each new feature ships; (2) **deployment mode** —
a new axis (self-hosted vs. SaaS) picking between two named routing
profiles, local-first vs. cloud-first; (3) **per-tenant override** — a
new, thin layer letting one company force "local only, never call out"
regardless of the deployment-mode default, which is what "privacy-
sensitive customers" actually requires; (4) **fallback chains** — the
mechanism (`RoutingDecision.fallbacks`) already exists and is unused;
populate it (e.g. local-first with an explicit, opt-in cloud fallback on
provider failure); (5) **evaluation-informed defaults** — which
provider/model is the default for a given capability should come from
measured quality/cost/latency data (Phase 3), not from whoever built the
feature guessing.

### 9. How should enterprise customers deploy the system?

Self-hosted, on their own infrastructure, with the AI provider defaulted
to a local model via an OpenAI-compatible local inference endpoint
(Ollama, vLLM, or their own hosted server) — zero data leaves their
network by default. Cloud fallback should exist only as an explicit,
per-capability opt-in they control, never an implicit default, because
some of these customers will have a compliance posture that makes even
an opt-in unacceptable for certain capabilities and fine for others
(e.g., "classify replies locally, but you may call Claude for
Personalization" is a legitimate real request this design needs to
support).

### 10. How should SaaS customers deploy the system?

Multi-tenant, centrally hosted by Sales-Agent4, defaulted to cloud
providers — because Sales-Agent4-as-vendor should not take on shared GPU
fleet ops at this stage of the company. Cost control here should come
from real per-tenant budget ceilings (missing today — Phase 3 builds
this) and from picking the cheapest adequate model per capability (Reply
Intelligence classification doesn't need Sonnet-tier reasoning), not
from forcing SaaS tenants onto immature local inference before the
volume justifies owning it. A centrally-hosted small local model for
high-volume/low-stakes SaaS tasks is a legitimate later optimization
(Phase 4), once real usage data says it's worth it — not a day-one
requirement.

### 11. What architecture would still be the best choice 5–10 years from now?

The one you already have the bones of: a Gateway where "which model runs
this capability" is a *configuration* decision, resolved per capability,
per deployment mode, and per tenant — never a code decision baked into
a feature. Add to it: a first-class local/self-hosted provider client
speaking the OpenAI-compatible wire protocol (so it works with whatever
serving tool wins over the next decade without bespoke code per tool), a
real evaluation harness so provider choice is continuously re-measured
rather than decided once and calcified (both cloud and open models will
look completely different in five years — hardcoding today's "best"
choice, cloud OR local, would be the actual long-term mistake), real
cost observability wired end-to-end, and a standing discipline that
"should this even be AI, or should it stay deterministic" is asked for
every new capability, not assumed. That is architecture-as-
configuration. It's most of what's already built. The answer to "redesign
or extend" is extend.

---

## 3. Coupling audit — every place the code is coupled to Claude or a specific provider

| # | Coupling point | Problem or acceptable? | Decoupling difficulty | Recommendation |
|---|---|---|---|---|
| 1 | `ROUTING_POLICY` has exactly one entry, `"default" → claude`, zero fallbacks | Acceptable as the documented "day one" state, not acceptable to leave indefinitely — every future capability silently shares this one chain with no isolation | **Trivial** — pure data change, no code, no migration | Register one explicit entry per real capability as it ships (Phase 1) |
| 2 | `research_analysis` has no entry of its own — it rides the shared `"default"` entry | Minor problem — means Research can't be independently routed without affecting whatever else later shares `"default"` | **Trivial** | Add the explicit entry now, before more capabilities exist to collide with it (Phase 1) |
| 3 | No local-model `ProviderClient` exists at all | **The real blocker** to your stated goal — not any Claude-specific hardcoding | **Low-moderate** — Ollama/vLLM/LM Studio/text-generation-webui all speak the OpenAI chat-completions wire format already, so `OpenAIProviderClient` is already ~90% of the code needed; make its `base_url` configurable and register a `"local"` provider_key | Build a generalized OpenAI-*compatible* client, parameterized by `base_url`, not a bespoke per-tool integration (Phase 1) |
| 4 | Structured-output/JSON-mode handling differs materially per provider (Claude: prompt-engineered + raw-text-parsed; OpenAI: native `response_format`; Gemini: its own JSON mode) | Real technical risk — smaller local models will likely have a meaningfully higher malformed-JSON rate for the same prompt, silently degrading Research Intelligence quality (safely, via the existing RETRY/degrade path, but *silently*) | **Moderate** — the safety net already exists; making local structured output *reliable* (not just non-crashing) needs either grammar-constrained decoding support from the serving layer or a measured tolerance for a higher retry/degrade rate | Don't guess — measure per capability before defaulting anything to local (Phase 3's evaluation harness) |
| 5 | Cost accounting price table is empty; `LLMAnalysisEngine` never persists `token_usage`/`api_cost` even though the DB columns exist | Real problem, independent of provider choice — you cannot manage the recurring-cost risk you're worried about with zero cost visibility today, even on Claude | **Low** — the data (`AgentExecutionResult.usage`) already flows through the stack, unused; wire it into the two existing columns | Fix this regardless of anything else in this plan (Phase 1) |
| 6 | No per-tenant/per-company budget ledger or enforcement; `BudgetExceededError` declared, never raised | Real problem — blocks safe SaaS-tier cost control at any scale, let alone "thousands of companies" | **Moderate** — needs a new ledger table + a hard pre-flight check, both already anticipated in existing docstrings as deferred, not forgotten | Build in Phase 3, ship opt-in per tenant so no one's existing behavior silently changes |
| 7 | Only one real Agent/capability exists in the whole system (`research_analysis`) | Not a problem — it's the opportunity. The blast radius of today's Claude-coupling is exactly one optional, off-by-default feature | N/A | This is *why* to act now rather than later: fix the pattern once, before four more domains each independently invent (or hardcode) their own AI integration |
| 8 | `ResponseFormat` only models `TEXT`/`JSON`, no explicit schema-enforced/grammar-constrained mode | Minor, forward-looking gap — not urgent today (Anthropic's own tool-forced-schema mode is already named as deferred v1 simplification) | **Moderate**, later | Revisit when a specific local model's JSON reliability demonstrably needs it — don't build speculatively now |

---

## 4. Proposed architecture (extension, not a redesign)

### 4.1 Current architecture (as built)

```
 Workflow Action / Route
        │
        ▼
  AgentRuntime.run()
        │  (get_agent → resolve_execution_policy)
        ▼
   Agent.build_context()  ──►  PromptContext (business content only)
        │
        ▼
  PromptBuilder.build(context, policy) ──► GatewayRequest
        │
        ▼
  AIGateway.complete(request)
        │  ProviderRouter.select(request.capability)
        │        │
        │        ▼
        │  ROUTING_POLICY = { "default": RoutingDecision(primary="claude") }
        │        │  (EVERY capability falls through to this one entry)
        │        ▼
        │  PROVIDER_CLIENT_REGISTRY = {claude, openai, gemini}  (all real, only "claude" ever reached)
        ▼
   ClaudeProviderClient.complete() ──► real Anthropic API call
        │
        ▼
   GatewayResponse ──► Agent.interpret() ──► AgentOutput
```

Strength: the vertical spine (Agent → PromptBuilder → Gateway → Router →
ProviderClient) is genuinely provider-neutral. Weakness: the ROUTING_POLICY
box is a single point, and there's no local-model box to route to at all.

### 4.2 Proposed architecture (additive)

```
                     ┌─────────────────────────────────────────┐
                     │        Capability + Deployment Router      │
                     │                                             │
Agent → PromptBuilder│  1. capability      (e.g. "research_analysis")
        → GatewayReq │  2. deployment_mode (self_hosted | saas)   │
                     │  3. tenant override (CompanyProfile-scoped)│
                     │  4. fallback chain  (RoutingDecision.chain)│
                     └───────────────────┬─────────────────────┘
                                         │
                     ┌───────────────────┼───────────────────────┐
                     ▼                   ▼                       ▼
           ClaudeProviderClient  OpenAIProviderClient   LocalProviderClient (NEW)
             (unchanged)            (unchanged)         (OpenAI-compatible wire
                                                          protocol, configurable
                                                          base_url → Ollama / vLLM /
                                                          LM Studio / anything that
                                                          speaks it)
                     │                   │                       │
                     └───────────────────┴───────────────────────┘
                                         │
                                         ▼
                              GatewayResponse (unchanged shape)
                                         │
                                         ▼
                      Cost ledger write (NEW) — per-company running total,
                      feeds a real pre-flight budget check (NEW)
```

Everything below "Capability + Deployment Router" and above
"GatewayResponse" is unchanged. The new pieces are: one new provider
client, one router upgrade (still capability-keyed, now also
deployment-mode- and tenant-aware), and a cost ledger that finally uses
data the stack already produces.

### 4.3 Local model integration strategy

Don't write an Ollama-specific SDK integration. Ollama, vLLM, LM Studio,
and text-generation-webui all implement the OpenAI chat-completions wire
format today. Generalize the existing `OpenAIProviderClient` pattern into
a client that accepts a configurable `base_url` (and an optional,
often-ignored API key), register it under a `"local"` provider_key (or
several — `"local_fast"`, `"local_quality"` — if a deployment runs more
than one local model for different capabilities). This means "add
support for a new local serving tool" is a config change, not a new
integration, for as long as that tool speaks the OpenAI protocol —
which is the safest bet for a 5–10 year horizon, since that protocol has
become the de facto standard interface regardless of which specific
tool wins.

### 4.4 Cloud provider integration strategy

No change — `ClaudeProviderClient`/`OpenAIProviderClient`/
`GeminiProviderClient` stay exactly as they are. The only cloud-side
work is making them properly *reachable* per capability/tenant (routing
config) and properly *measured* (cost ledger), not touching their
internals.

### 4.5 Configuration strategy

- `AI_DEPLOYMENT_MODE`: `"saas" | "self_hosted"` — selects a named
  routing profile (two small, explicit dicts, not a rewrite of
  `ROUTING_POLICY`'s mechanism).
- `LOCAL_MODEL_BASE_URL` / `LOCAL_MODEL_DEFAULT_MODEL` /
  `LOCAL_MODEL_API_KEY` (optional) — same "unset until configured,
  lazy-checked" convention every other provider setting already follows.
- Per-`CompanyProfile` AI provider override — a new, small, optional
  field/table, consulted only if present; absent means "use the
  deployment-mode default," so nothing changes for anyone who doesn't
  set it.
- `AI_GATEWAY_BUDGET_ENFORCEMENT_ENABLED` (per tenant or global) — opt-in
  flag gating the new hard budget check, so existing soft-log-only
  behavior is preserved until a tenant explicitly turns it on.

### 4.6 Deployment strategy

- **Enterprise / self-hosted**: `AI_DEPLOYMENT_MODE=self_hosted`, local
  model configured as primary for every capability, cloud providers
  configured only as an explicit, per-capability opt-in fallback (or
  omitted entirely for compliance-locked tenants).
- **SaaS**: `AI_DEPLOYMENT_MODE=saas`, cloud providers as primary, per-
  tenant budget ceilings enforced, cheapest-adequate-model-per-capability
  chosen using Phase 3's evaluation data. A shared, centrally-hosted
  small local model for high-volume/low-stakes capabilities (e.g. Reply
  Intelligence classification) is a legitimate Phase 4 optimization once
  volume justifies the ops investment — not a day-one requirement.

### 4.7 Migration strategy

Every change below is additive and defaults to today's exact behavior.
Nothing is removed. No existing feature's default changes. This is the
same discipline already proven twice in this codebase (the Phase 2
provider-visibility UX work, and Phase 3's own `deterministic`-by-default
engine swap) — extended, not reinvented.

---

## 5. Migration Plan v2

### Phase 1 — Foundations: cost visibility, local provider client, capability hygiene

**What changes:**
- Populate `AIAnalysis.token_usage`/`api_cost` from
  `AgentExecutionResult.usage` (already computed, currently discarded).
- Build a generalized OpenAI-compatible `ProviderClient` with a
  configurable `base_url`; register it as `"local"` in
  `PROVIDER_CLIENT_REGISTRY`; add `LOCAL_MODEL_BASE_URL` /
  `LOCAL_MODEL_DEFAULT_MODEL` / `LOCAL_MODEL_API_KEY` settings.
- Register an explicit `"research_analysis"` entry in `ROUTING_POLICY`
  (currently implicit via `"default"`).

**Why:** these are the cheapest, lowest-risk, highest-leverage fixes.
They make "try a local model at all" possible for the first time, close
a real observability gap that already undermines your cost-consciousness
goal today (even on Claude), and stop the next capability from silently
sharing Research's routing entry.

**Complexity:** Low. No schema migration, no behavior change for any
existing feature, all additive.

**Maintenance impact:** Low — mirrors patterns (registry + config flag)
already proven twice in this codebase.

**Compatibility risk:** None. `RESEARCH_ANALYSIS_ENGINE_BACKEND` stays
`"deterministic"` by default; nothing forces local usage; existing cloud
behavior is untouched.

### Phase 2 — Deployment-mode-aware routing + per-tenant override

**What changes:**
- `AI_DEPLOYMENT_MODE` setting selecting between a `self_hosted` routing
  profile (local-first, explicit opt-in cloud fallback) and a `saas`
  profile (cloud-first, as today).
- A per-`CompanyProfile` AI provider preference (optional; absent means
  "use the deployment-mode default").
- Populate real fallback chains (`RoutingDecision.fallbacks`) instead of
  the currently-empty list.

**Why:** this is what turns "enterprise self-hosted with local models,
SaaS with cloud" from a stated goal into an actual, configurable
capability — and gives a specific tenant the ability to say "never call
out to the cloud for this capability," which privacy-sensitive customers
will need.

**Complexity:** Moderate — one new resolution layer inserted at the
point `ExecutionPolicy`/`RoutingDecision` are looked up, plus a small
schema addition for the per-tenant override. Still additive; nothing
existing is restructured.

**Maintenance impact:** Moderate — one more configuration axis to reason
about and test, mitigated by keeping the resolution logic in one thin,
well-tested function rather than scattering branches through call
sites.

**Compatibility risk:** Low — every existing deployment resolves exactly
as today (implicit `saas` mode, no per-tenant override) unless someone
explicitly configures otherwise.

### Phase 3 — Real budget enforcement + evaluation/benchmarking harness

**What changes:**
- A per-company spend ledger (new table) and a hard, opt-in pre-flight
  budget check in `AIGateway.complete()` — finally implementing the
  `BudgetExceededError` path that has been declared but unused since
  M7.2.
- An internal (non-user-facing) evaluation harness: run the same
  `AgentInput` through multiple providers/models for a given capability
  against a fixed set of representative test cases, and compare
  structured-output validity rate, latency, and cost (quality scoring
  added as it becomes practical).

**Why:** replaces "assume local models are fine" or "assume Claude is
required" with actual, capability-by-capability evidence, and gives you
the real cost control your "thousands of companies" worry actually
needs — which today doesn't exist regardless of provider.

**Complexity:** Moderate-high. The ledger + budget check is
straightforward engineering; the evaluation harness requires curating a
representative test-case set per capability, which is real product
effort, not just plumbing.

**Maintenance impact:** Moderate. The ledger needs the same care as any
financial-adjacent data. The evaluation harness is designed to be
re-run periodically as models change — that recurring re-run *is* the
point, not a one-time cost.

**Compatibility risk:** Low-moderate. Hard budget enforcement changes
real behavior once enabled for a tenant (a call that used to succeed
can now be rejected) — ship strictly opt-in per tenant, default to
today's soft-log-only behavior, so no one is silently broken.

### Phase 4 — Extend the proven pattern to every remaining domain

**What changes:** Personalization, Outreach, and Reply Intelligence each
get their own AI-backed engine, following the exact recipe Research
Intelligence already established: deterministic engine stays the
default, a second engine is added behind a registry + config flag, a
capability-specific routing entry is registered from day one (Phase 1's
hygiene), and the provider/model choice is informed by Phase 3's
evaluation data rather than guessed. Revisit whether a shared,
centrally-hosted small local model is worthwhile for high-volume,
low-stakes SaaS-tier tasks once real usage data justifies the ops
investment.

**Why:** consistency. The single biggest long-term maintenance risk of
*not* doing this is each domain inventing its own bespoke AI-integration
pattern — or worse, each hardcoding a slightly different provider
assumption independently, which is exactly the fragmentation this whole
review exists to prevent.

**Complexity:** Low per domain — by this point the pattern is proven
twice already (Research, and this plan's own Phases 1-3); each new
domain is an application of a known recipe, not a fresh design.

**Maintenance impact:** Low per domain, same reasoning.

**Compatibility risk:** Low — same "default unchanged, explicit opt-in"
discipline applied every time.

---

## 6. Direct answer to "should we redesign now?"

No full redesign. The Gateway/Agent/PromptBuilder split is a strong
foundation and should be preserved exactly as it is. But yes, do Phase 1
now, before Personalization/Outreach/Reply Intelligence get built —
it's a few days of low-risk, purely additive work, and it's
categorically cheaper to do once, now, than to retrofit after four more
domains have each shipped their own version of today's Claude-only
default. Phases 2-4 can follow at whatever pace matches when you
actually need enterprise self-hosted deployments and real SaaS cost
control — neither is blocking anything you're building this month, but
Phase 1 quietly is.

Awaiting your decision on scope/pacing before any implementation
resumes.
