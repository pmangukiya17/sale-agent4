# M2 Phase 3 — Buyer Discovery & Research Intelligence: Architecture Review + Implementation Plan

Status: **DRAFT — awaiting CEO approval. No code has been written for this phase.**

Scope note up front: the previously-approved provider table in
`m2-discovery-provider-strategy.md` names Phase 3 as "OpenCorporates +
multi-provider execution" (a second Search Provider). The CEO's latest
instruction explicitly redefines **M2 Phase 3** as *"significantly
increasing the intelligence of the Buyer Discovery & Research Engine."*
This document treats that as an intentional supersession, not something
to silently reconcile. Recommendation: renumber the old "OpenCorporates +
parallel execution" work to **Phase 4**, since it is unaffected by
anything below (Search Providers are explicitly out of scope here — see
Section 4). Flagging this explicitly rather than deciding it unilaterally.

## 1. What M1 and M2 have actually built (review)

**M1** — Company Profiles, Products, ICP Criteria, core auth, the
workflow/event backbone (Events, EventConsumption, Notifications,
Workflow Engine, background workers), CRM Automation.

**M2 Phase 1 (a/b/c)** — Discovery pipeline: `DiscoverySearch` →
`DiscoveryJob` → `DiscoveryRun`, dedup, normalization, scoring
(`app/discovery/scoring.py`, `ICPCriteria.rules["scoring_weights"]`),
Prospect → Opportunity import, job cancellation.

**M2 Phase 2** — External Research Provider Framework: `SearchService`,
`QueryPlanner` (products × countries, bounded at 50 variations),
`Provider Registry` (lazy-imported, `is_search_provider()`), first real
search provider (`BraveSearchProvider`), retryable `ProviderError`
hierarchy, per-provider-run telemetry.

**M2 Phase 2 UX follow-up** — Provider visibility (`DiscoveryProviderService`,
`GET /discovery-providers`), honest Search Frequency/Depth controls,
provider badges on Prospects/Discovery Jobs.

**Research domain (already built, undocumented as a standalone
architecture doc until now)** — `ResearchRequest` → `ResearchJob` →
`run_research_request()`: fetches `RawDocument`s via
`app/research/providers/` (currently `manual_document` only), runs
`AIAnalysisEngine.analyze()` to produce `AnalysisOutcome`s per
`AIAnalysisType` (COMPANY_PROFILE / BUYER_PROFILE / BUSINESS_SIGNALS /
SALES_INTELLIGENCE), writes exactly one new `IntelligenceSnapshot`
version, creates `Signal`/`Recommendation` rows with `SignalEvidence`
linking back to source documents, and can render a `ResearchReport`.
Triggered manually today, or via the same M7 Workflow Action pattern as
Discovery (`ResearchExecutionAction`, key `research.execute_request`).

**The critical fact this review surfaces**: the only `AIAnalysisEngine`
that exists is `DeterministicAnalysisEngine` — a keyword/regex matcher.
Its own module docstring says so explicitly: *"no real LLM call
(explicitly forbidden for this milestone: no OpenAI/Claude/Gemini/Azure/
Ollama)."* Every "AI Analysis," "confidence score," and "reasoning"
string in the product today is a deterministic string template, not a
model output. The same is true one layer up: **M3 Personalization is
already fully built** (own models, own pipeline, own frontend pages) and
its `PersonalizationEngine` has the identical deterministic-stub-only
restriction. Neither domain has ever called the AI Gateway.

Separately, the **AI Gateway** (`app/ai_gateway/` — client, router,
request/response types, error hierarchy, cost accounting) and the
**Agent framework** (`app/ai_agents/` — `Agent` ABC, `AgentRuntime`,
`AGENT_REGISTRY`) are fully built, reviewed, and stable — and have
**zero production callers**. `AGENT_REGISTRY` is an empty dict today.
The `Supervisor` framework (`app/supervisor/`) is likewise built with
zero concrete implementations and no persistence table for
`SupervisionState` yet.

## 2. Biggest remaining gaps

1. **No real intelligence anywhere in the Research or Personalization
   layers.** Every Signal, Recommendation, and Intelligence Snapshot
   field is produced by fixed keyword rules. This is the single biggest
   gap relative to the product's own name ("AI Sales Operating System")
   and is exactly what the CEO's brief calls out ("significantly
   increasing the intelligence").
2. **A fully-built AI Gateway/Agent stack has never been proven under a
   real call.** This is a real risk, not just a gap: PromptBuilder
   output shape, GatewayResponse parsing for structured JSON, retry/
   timeout behavior, and cost accounting are all currently unverified by
   any production usage.
3. **Research findings never feed back into Discovery.** `Prospect.total_score`
   is written once, during `run_discovery_search()`'s scoring pass, and
   never revisited. A prospect that Research later finds is expanding
   internationally (a `Signal` with `importance=CRITICAL`) sits at
   whatever score Discovery gave it on day one — the two systems don't
   talk to each other today.
4. **`Prospect` has no ORM relationship to `Signal`/`Recommendation`/
   `IntelligenceSnapshot`/`ResearchReport`** — everything is queried by
   `prospect_id`. Not necessarily a defect, but worth naming.

## 3. Phase 3 objective

Make the Research layer's intelligence **real** — by giving it its first
genuine, LLM-backed `AIAnalysisEngine`, built as the first concrete
`Agent` through the already-built (never-used) AI Gateway/Agent stack —
while preserving every existing interface, schema, table, route, and
workflow wiring so the swap is invisible to everything downstream. Close
the one concrete structural gap discovered (Research findings never
influence Discovery standing) with a conservative, additive mechanism
that never becomes a second writer of `Prospect.total_score`.

Two deliverables, deliberately narrow:

- **3A — LLMAnalysisEngine**: a second `AIAnalysisEngine` implementation,
  selected by a new config flag, default unchanged (`deterministic`).
- **3B — Signal-aware prospect priority**: a read-time, non-persisted
  synthesis of `total_score` + recent high-importance Signals, surfaced
  as one additional field — never mutating `total_score` itself.

Explicitly **not** in scope: Search Providers, Query Planner, multi-
provider parallel execution (that is the renamed Phase 4), Supervisor-
driven multi-agent orchestration, and any change to Personalization
(same treatment, later phase, same pattern — see Section 4).

## 4. How Phase 3 integrates with each named area

- **Discovery Jobs / Search Providers / Query Planner**: untouched.
  Phase 3 only reads `Prospect` rows Discovery already produced.
- **Research Reports**: unchanged shape (still rendered from a
  snapshot). Content quality improves because the snapshot it's
  rendered from is now genuinely AI-produced.
- **Intelligence Snapshots**: unchanged schema. `AIAnalysisEngine`'s own
  docstring already anticipated this exact swap — *"zero schema or
  pipeline change... provided it honors the `structured_output` contract
  documented per `AIAnalysisType`."* `LLMAnalysisEngine` targets that
  same contract; nothing about `run_research_request()` changes.
- **Signals**: unchanged schema. Now genuinely produced by a model's
  reasoning over real `RawDocument`s, with real `confidence`/`reasoning`
  instead of fixed keyword-match text. New: a bounded, additive read-time
  link into Discovery scoring (3B).
- **Future AI Personalization (M3)**: not touched in Phase 3. Its
  `PersonalizationEngine` carries the identical deterministic-stub
  restriction as Research's does, so the interface-preserving-swap
  pattern this phase establishes is the direct template for
  Personalization's own equivalent swap in a later phase — no redesign
  needed then. Named explicitly so this isn't rediscovered from scratch
  later.

## 5. Architectural weaknesses challenged before implementation

1. **First production use of AI Gateway/Agents.** Untested assumptions
   (structured-output parsing, retry policy, cost accounting under a
   real call) are a real risk. Mitigation: config-gated rollout
   (`RESEARCH_ANALYSIS_ENGINE_BACKEND`, default `"deterministic"`,
   exact same shape as the existing `REPLY_CLASSIFIER_BACKEND` pattern
   in `app/reply_intelligence/classifiers/registry.py`), and a single
   `Agent` — not a `Supervisor`-orchestrated multi-agent flow — since
   `SupervisionState` has no persistence table yet and no concrete
   `Supervisor` has ever shipped. Proving one Agent in production is the
   correct-sized step; multi-agent orchestration is future scope.
2. **LLM calls are genuinely fallible and slow — the deterministic stub
   never was.** Research's pipeline has never had to handle a real
   external-call failure. Recommendation: mirror Discovery's own
   resilience precedent — catch `GatewayError`, record it on the
   `ResearchJob`/`AIAnalysis` row, degrade that one analysis type rather
   than failing the whole job.
3. **Human review state must never be silently reset.** A `Signal` or
   `Recommendation` a human already reviewed/dismissed must stay that
   way. Because `IntelligenceSnapshot` is already append-only/versioned
   and `Signal.intelligence_snapshot_id` is per-version, a new analysis
   run naturally produces new rows rather than mutating reviewed ones —
   this is confirmed as an existing invariant, not something Phase 3
   needs to build, but it is called out here as a hard constraint on the
   implementation.
4. **The `Prospect.total_score` "second writer" risk.** Directly
   updating `total_score` from Research would create two independent
   writers of the same field and could conflict with Discovery's own
   "never re-score a prospect a human has already acted on" rule
   (`pipeline.py`'s terminal-status guard). Rejected. Recommendation:
   3B is **read-time only** — computed at serialization, never
   persisted, never touching `total_score`. Presented as a considered
   choice among three options (do nothing / additive read-time field /
   full automatic re-scoring) — recommending the middle option, not
   deciding the third unilaterally.
5. **No per-workspace feature flag exists** — `RESEARCH_ANALYSIS_ENGINE_BACKEND`
   would be a single global setting, same limitation as
   `BRAVE_SEARCH_ENABLED` today. Named as a real limitation for gradual
   rollout; scoping a per-company flag is offered as a separate, small
   follow-up if wanted, not bundled here.

## 6. Extend vs. build new

- **Extend** `app/research/analysis/` with a second `AIAnalysisEngine`
  implementation — do not touch `base.py`'s contract.
- **Add** a small registry (`app/research/analysis/registry.py`),
  mirroring `app/reply_intelligence/classifiers/registry.py` exactly —
  this module doesn't exist yet today (confirmed: `pipeline.py` line 256
  currently constructs `DeterministicAnalysisEngine()` directly). This
  is the one genuinely new piece of plumbing, and it is copying an
  established, approved pattern, not inventing one.
- **Extend** `app/ai_agents/` with the first concrete `Agent` subclass —
  this is precisely what that package was built for and has been idle
  waiting on.
- **Do not** introduce `Supervisor` usage, new Workflow Actions, or a new
  `WorkflowDefinition` — `ResearchExecutionAction` and its single-step
  workflow are unaffected; the engine swap happens entirely inside
  `run_research_request()`.
- **Do not** add an ORM relationship from `Prospect` to `Signal`/etc. —
  the read-time synthesis in 3B queries by `prospect_id`, same as every
  existing caller does today.

## 7. Database impact

**Zero required migrations.** Every column `LLMAnalysisEngine` needs
already exists on `AIAnalysis` (`model_used`, `prompt_version`,
`raw_model_output`, `structured_output`, `confidence`, `reasoning`).
3B is computed at read time — no new column on `Prospect`.

One **optional, non-blocking** addition to consider separately: an
`agent_key` column on `AIAnalysis` for clearer audit of which `Agent`
class (not just which model) produced a row. Not required for Phase 3;
flagged as a nice-to-have, not bundled into this migration-free plan.

## 8. Backend impact

- New: `app/ai_agents/research_analysis_agent.py` — `ResearchAnalysisAgent(Agent)`.
  `build_context()` assembles Prospect/Company/Product/RawDocument
  content into a `PromptContext` (business content only, per `Agent`'s
  own contract — no provider/model/temperature reachable from this
  method). `interpret()` parses a `GatewayResponse` into the exact
  `structured_output` shape `base.py`'s docstring already defines per
  `AIAnalysisType`.
- New: `app/research/analysis/llm_engine.py` — `LLMAnalysisEngine(AIAnalysisEngine)`.
  `analyze()` invokes `AgentRuntime.run()` against `ResearchAnalysisAgent`
  once per `AIAnalysisType` needed, maps the resulting `AgentOutput` into
  `AnalysisOutcome` objects — the same return shape
  `DeterministicAnalysisEngine` already produces.
- New: `app/research/analysis/registry.py` — `get_analysis_engine()`,
  keyed by `settings.RESEARCH_ANALYSIS_ENGINE_BACKEND`, default
  `"deterministic"`. `pipeline.py` line 256 changes from constructing
  `DeterministicAnalysisEngine()` directly to calling
  `get_analysis_engine()` — a one-line call-site change, not a pipeline
  redesign.
- New config (`app/core/config.py`): `RESEARCH_ANALYSIS_ENGINE_BACKEND: str = "deterministic"`.
- New (read-time only, 3B): a small pure helper — e.g.
  `app/research/priority.py`'s `compute_signal_adjusted_priority(prospect, signals)`
  — combining `total_score` with any `NEW`/`HIGH`-or-`CRITICAL` Signal
  into a derived value, never persisted.

## 9. Frontend impact

No required structural change. `ProspectResearch.tsx` already renders
`model_used`/`confidence`/`reasoning` — these fields simply become
meaningful instead of stub text. If 3B is approved: one additional,
clearly-labeled annotation near the existing score on `Prospects.tsx`
and `ProspectResearch.tsx` (e.g. "Signal-adjusted priority" next to,
never replacing, the stored score).

## 10. API changes

None breaking. If 3B is approved: one additive, optional field on the
existing Prospect read schema (e.g. `signal_adjusted_priority: float | None`,
`signal_priority_note: str | None`) — computed at serialization time,
backward compatible for any existing client.

## 11. Workflow changes

None. `ResearchExecutionAction` (key `research.execute_request`) and its
`WorkflowDefinition` are unchanged — the engine selection happens fully
inside `run_research_request()`, invisible at the Workflow Engine layer.
This is a deliberate design strength worth naming: the workflow-wiring
risk of this phase is zero.

## 12. Risks and trade-offs (consolidated)

| Risk | Mitigation |
|---|---|
| First real AI Gateway/Agent production use | Config-gated backend, default unchanged, single Agent not Supervisor |
| Real LLM calls are slow/fallible | Catch `GatewayError` per analysis type, degrade not crash, mirrors Discovery's own per-provider isolation |
| Structured-output parsing may fail | `ai_gateway.request`'s existing `ResponseFormat` support + `AgentOutcome.RETRY`'s existing bounded retry loop in `AgentRuntime` |
| Second writer of `Prospect.total_score` | Rejected; 3B is read-time-only, never persisted |
| No per-workspace flag yet | Named limitation; offered as separate follow-up |
| Real API cost | No automatic/recurring re-analysis — stays explicitly triggered exactly as today, consistent with the Phase 2 UX decision to leave automation out of scope |

## 13. Testing strategy

- Pure/mocked unit tests for `ResearchAnalysisAgent.build_context()`/
  `interpret()` — no DB, no network, genuinely executable in this
  sandbox (same `TYPE_CHECKING` discipline already used elsewhere).
- `LLMAnalysisEngine` tested against a fake `GatewayResponse` (no real
  provider call) proving it maps into the same `AnalysisOutcome` shape
  the deterministic engine already produces.
- DB-backed integration test (disclosed as Docker-only, same disclosure
  convention as every prior phase) proving `run_research_request()` with
  `RESEARCH_ANALYSIS_ENGINE_BACKEND=llm` (mocked Gateway) produces a
  structurally identical Snapshot/Signal/Recommendation row set to the
  deterministic path's own existing tests.
- Full regression requirement: every existing Research/Discovery test
  must stay green with the default config unchanged.
- Real end-to-end verification against a live model API key is a CEO/
  Docker-environment step this sandbox cannot perform (no network, no
  API key here) — disclosed up front, same as `BraveSearchProvider`'s
  own disclosed gap in Phase 2.

## 14. Rollout plan

1. Land `ResearchAnalysisAgent` + `LLMAnalysisEngine` + registry + config
   flag, default `"deterministic"` — zero behavior change, fully
   shippable on its own.
2. CEO/ops flips `RESEARCH_ANALYSIS_ENGINE_BACKEND=llm` in a non-
   production environment with a real API key configured.
3. Manually compare generated Signals/Recommendations/Snapshots against
   the deterministic baseline for quality.
4. Once confident, flip the default in a small, separately-approved
   follow-up commit — not bundled with the initial build.
5. (Future, not this phase) repeat the identical pattern for
   Personalization's own engine; revisit 3B's rollout if approved.

---

Awaiting explicit approval before any code is written, per standing
process. Open decision point for the CEO specifically: confirm the
Phase 3/Phase 4 renumbering in the scope note above, and confirm 3B
(signal-adjusted priority) is wanted in this phase or should be deferred
to keep Phase 3 to 3A only.

## Addendum — rollout step 4 executed (default flip)

3A (this document's own scope) was approved and shipped: commits
`8c2fa6b` (this plan), `17d297c` (ResearchAnalysisAgent + LLMAnalysisEngine
+ registry/config flag + observability UX), `94f0569` (E2E test mapper-
registration fix). 3B (signal-adjusted priority, Section 8) was never
separately approved and remains deferred - not built.

Per this document's own Section 14 "Rollout plan," step 4 says: *"Once
confident, flip the default in a small, separately-approved follow-up
commit - not bundled with the initial build."* The CEO has now
explicitly approved that flip: `RESEARCH_ANALYSIS_ENGINE_BACKEND`'s
default in `app/core/config.py` changed from `"deterministic"` to
`"llm"`. `"deterministic"` remains fully selectable (config-only).

This lands after, and composes with, the M11 AI Provider Hierarchy work
(`docs/architecture/m11-ai-provider-hierarchy-plan.md`) - the Premium
Approval Gate (`AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL`, default `True`)
still governs every LLM-backed research run: an environment with no
local/free provider configured degrades to a "needs premium approval"
result rather than raising or silently calling a paid provider. See
`app/research/analysis/llm_engine.py`'s `PREMIUM_APPROVAL_REASONING_PREFIX`.

One test (`tests/test_research_workflow_e2e.py`) and one operational
script (`smoke_test.py`'s "M2 checks: AI Research & Prospect
Intelligence" section) specifically exercise the deterministic
keyword-stub path and have been updated/annotated accordingly rather
than left silently broken by this default change - see their own
inline comments.
