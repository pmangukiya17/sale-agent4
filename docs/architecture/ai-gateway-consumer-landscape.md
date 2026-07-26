# AI Gateway Consumer Landscape — Provider-Neutral AI Gateway v1

Companion reference to `docs/architecture/provider-neutral-ai-gateway-plan.md`
(the milestone-by-milestone build log for M-AIGW-1 through M-AIGW-5, all
CEO-approved and shipped). That document records *how the Gateway was
built*; this one records *how every AI-consuming domain — shipped or
future — relates to it*, requested before scoping the next major AI
milestone.

**Status: Provider-Neutral AI Gateway v1 — complete, approved.** Every
claim below reflects the actual codebase as of this writing, not a
target state.

## 1. The layering, unchanged since M7.2, now proven twice

```
Workflow Engine -> Workflow Action -> [Supervisor ->] Agent Runtime -> Prompt Builder -> AI Gateway -> Provider Router -> Provider Clients (Claude/OpenAI/Gemini/Groq/Local)
```

Every arrow points one direction only. A concrete Agent (`ResearchAnalysisAgent`,
`OutreachEmailAgent`) never imports `app.ai_gateway`/`app.prompt_builder`
directly — it only implements `Agent.build_context()`/`interpret()`
(`app/ai_agents/base.py`). `AgentRuntime` (`app/ai_agents/runtime.py`) is
the only code that calls both `PromptBuilder.build()` and
`AIGateway.complete()`. `ProviderRouter`/`PROVIDER_CLIENT_REGISTRY`
(`app/ai_gateway/router.py`/`providers/registry.py`) are the only code
that knows concrete provider identities. `anthropic`/`openai`/
`google.genai`/`groq` are importable ONLY inside
`app/ai_gateway/providers/*_client.py` — enforced by a repeatable grep
(`registry.py`'s own docstring), not just a convention.

## 2. The neutrality guarantee is structural, not conventional

Three mechanisms make "a domain can't accidentally couple to a
provider" true by construction, not by discipline:

- **`Agent`'s two-method split.** `build_context(input_data) -> PromptContext`
  and `interpret(response, input_data) -> AgentOutput` are the *entire*
  surface a concrete Agent implements. Neither method's signature can
  even reach a provider name, model id, temperature, or token limit —
  those live only in `ExecutionPolicy` (`app/prompt_builder/policy.py`),
  resolved by `AgentRuntime`, never touched by the Agent itself.
- **Capability-based routing, never provider-name routing.** Every Agent
  declares a `provider_capability` string (`ExecutionPolicy.provider_capability`)
  — `research_analysis`, `outreach_email_generation`. Neither is a
  provider name; `CAPABILITY_PROVIDER_PREFERENCE` (`router.py`) maps
  capabilities to preference-ordered provider_key lists, and an
  unrecognized capability falls through to the `"default"` list by
  design. Adding a new AI-consuming domain has never once required a
  `router.py` change.
- **Registries as the one seam a domain adds.** Every domain that wants
  a swappable AI backend gets ONE small `registry.py` (backend_key ->
  class) selected by ONE settings flag — never a change to
  `AIGateway`/`ProviderRouter`/`PromptBuilder`/`AgentRuntime` themselves.
  This is the pattern proven twice below (Research, Outreach) and
  already staged a third time (Reply Intelligence).

## 3. Per-domain status

### 3.1 Research — shipped (M2 Phase 3)

- Agent: `ResearchAnalysisAgent` (`app/research/analysis/llm_agent.py`),
  capability `research_analysis`. Response shape: one combined JSON
  object with four fixed, always-present sections (`company_profile`/
  `buyer_profile`/`business_signals`/`sales_intelligence`).
- Registry/flag: `ANALYSIS_ENGINE_REGISTRY` (`{"deterministic":
  DeterministicAnalysisEngine, "llm": LLMAnalysisEngine}`), selected by
  `settings.RESEARCH_ANALYSIS_ENGINE_BACKEND` — **default `"llm"`**
  (flipped from `"deterministic"` in a separate, later, explicitly
  approved commit after the engine had shipped and been reviewed).
- Caller: `LLMAnalysisEngine` (`llm_engine.py`), the ORM -> primitives
  boundary; `run_research_request()` (`pipeline.py`) is the one call
  site, via `get_analysis_engine()`.
- Degrade path: on `PremiumApprovalRequiredError` or Gateway failure,
  returns four `AnalysisOutcome`s with `confidence=None` and a
  greppable `PREMIUM_APPROVAL_REQUIRED: ` reasoning prefix — never
  raises.

### 3.2 Outreach — shipped (M-AIGW-5)

- Agent: `OutreachEmailAgent` (`app/outreach/channels/llm_agent.py`),
  capability `outreach_email_generation`. Response shape: a
  **variable-length list of per-block content** (`{"subject": str,
  "blocks": [{"block_key", "content", "reasoning"}, ...]}`) —
  deliberately different from Research's fixed-section shape, proving
  the Agent/Gateway/PromptBuilder stack isn't specialized to Research's
  one problem shape.
- Registry/flag: `CHANNEL_BACKEND_REGISTRY["email"]` (`{"deterministic":
  EmailChannelProvider, "llm": LLMEmailChannelProvider}`), selected by
  `settings.OUTREACH_EMAIL_CHANNEL_BACKEND` — **default
  `"deterministic"`**, matching Research's own original Phase 3 rollout
  convention (default old behavior first; flipping the default is a
  separate future decision, not bundled into the milestone that adds
  the seam).
- Caller: `LLMEmailChannelProvider` (`llm_email_provider.py`). FIXED
  playbook blocks (legal disclaimers, unsubscribe links) are rendered
  deterministically and **never sent to the model**, regardless of
  which backend is selected — a real product-correctness boundary, not
  an optimization.
- Degrade path: identical shape to Research's — FIXED blocks still
  render correctly, AI blocks get an honest low-confidence placeholder,
  same `PREMIUM_APPROVAL_REQUIRED: ` prefix convention.

### 3.3 Personalization (buyer-strategy synthesis) — future, no seam yet

- Only implementation: `DeterministicPersonalizationEngine`
  (`app/personalization/engine/deterministic_stub.py`), rule-based
  scoring + templated narrative, `model_used = "deterministic-strategy-stub"`.
- **No registry, no config flag exists today.** `run_personalization_request()`
  (`app/personalization/pipeline.py`) directly constructs
  `DeterministicPersonalizationEngine()` — unlike Reply Intelligence
  (below), there is no drop-in seam yet. A future LLM engine for this
  domain requires building the seam from scratch (new `registry.py`,
  a `PERSONALIZATION_ENGINE_BACKEND` setting, and replacing the direct
  construction with a `get_personalization_engine()` call) before an
  Agent can even be added — genuinely new design surface, sized
  similarly to what M-AIGW-5 did for Outreach.
- Not scoped or started. Distinct from Outreach (which M-AIGW-5
  targeted) — see the plan doc's Section 12 scoping note for why these
  two are easy to conflate.

### 3.4 Reply Intelligence — future, seam already built and waiting

- Only implementation: `RulesReplyClassifier`
  (`app/reply_intelligence/classifiers/rules_classifier.py`), an
  ordered list of regex rule-sets (out-of-office -> negative ->
  positive -> neutral default), zero network calls.
- **Registry/flag already exists**: `REPLY_CLASSIFIER_REGISTRY`
  (`app/reply_intelligence/classifiers/registry.py`), selected by
  `settings.REPLY_CLASSIFIER_BACKEND` (default `"rules"`) — the exact
  same plugin-registry shape as Research's/Outreach's, built at the
  same time as the rest of this project's provider/classifier registry
  family, explicitly documented as ready for "openai/claude/gemini/a
  local-model backend" later. `ReplyClassificationResult` already
  carries an optional `reason: str | None` field reserved for an AI
  classifier's explanation text.
- Wired from `reply_intelligence_worker.py` (the M6.4 polling process)
  via `get_reply_classifier()` — adding an LLM-backed classifier here is
  the smallest lift of any domain in this list: a new `ReplyClassifier`
  subclass + Agent + one registry entry + flipping the setting, zero
  worker change. The worker's own docstring already flags the one real
  cost implication of doing so (today's cheap full-recompute-per-tick
  would need a cursor once classification stops being free).
- Not scoped or started — the seam being ready is not the same as a
  business decision to build the Agent.

### 3.5 Multi-Agent orchestration (Supervisor) — future, real infra, zero concrete plans

- `app/supervisor/` is genuinely built, not scaffolding:
  `SupervisorRuntime` (`runtime.py`) runs a real `step()`/
  `run_to_suspension()` execution loop, dispatching `RUN_AGENTS`
  decisions through `AgentRuntime.run_with_metadata()` (concurrently via
  a `ThreadPoolExecutor` when a decision names independent agents),
  validating every decision against depth limits and an
  allowed-agent-key allowlist (`plan_validation.py`), and persisting
  immutable `SupervisionState` history. `SUPERVISOR_REGISTRY`
  (`registry.py`, versioned by `(plan_key, version)`) is real and
  working.
- **Zero concrete `Supervisor` implementations are registered.** No
  actual multi-agent plan runs in production today — this is fully
  built infrastructure with nothing plugged into it yet, confirmed by
  this project's own AI-layer architecture review.
- Gateway-neutral for free, by construction: `Supervisor.decide_next()`'s
  signature (`SupervisionState in, SupervisorDecision out`) cannot reach
  `AgentRuntime`/`AIGateway`/`PromptBuilder`/any Agent instance — a
  Supervisor implementation only ever decides WHICH registered
  agent_keys to run next, never how they reach a model. The package's
  only AI-stack import is `app.ai_agents` (for `TokenUsage`/`AgentOutput`
  typing), never `app.ai_gateway`/`app.prompt_builder` — a
  grep-checkable fact, same discipline as the provider-SDK import
  boundary.
- Bridges to the Workflow Engine via `SupervisorInvocationAction`
  (`app/workflow_actions/supervisor_invocation_action.py`) — the only
  file in `app/workflow_actions/` that imports `app.supervisor`.
  `app/workflow_engine/` itself has, and must always have, zero
  reference to `app.supervisor`/`app.ai_gateway`/`app.ai_agents`/
  `app.prompt_builder`.
- Disclosed gap: a Supervisor-driven `WAIT` has no automated wake path
  yet (`event_dispatcher_worker.py` only wakes the built-in
  `WaitForEventAction`, not `SupervisorInvocationAction`); a
  `RUN_SUB_PLAN` primitive for Supervisor-to-Supervisor composition was
  designed but deliberately not built, pending a real business need.

## 4. What's uniform across all five domains (the actual "reusable, not research-specific" evidence)

- **No domain imports a provider SDK.** Confirmed by the same grep rule
  in every milestone's own verification (`registry.py`'s own docstring
  rule, re-run for M-AIGW-3/4/5).
- **A capability key with no dedicated preference-list entry is not a
  bug.** `research_analysis` and `outreach_email_generation` both fall
  through to `CAPABILITY_PROVIDER_PREFERENCE["default"]` — this has
  never required a `router.py` change, and won't for Reply
  Intelligence's or Supervisor's eventual Agents either.
- **The premium-approval/degrade-not-crash contract is identical
  everywhere it's exercised.** `PremiumApprovalRequiredError` ->
  greppable `PREMIUM_APPROVAL_REQUIRED: ` reasoning prefix, never a
  raised exception a pipeline has to catch specially.
- **A domain's own registry/config-flag pair is the only thing that
  changes when a domain adopts the Gateway.** `AIGateway`,
  `ProviderRouter`, `PromptBuilder`, and `AgentRuntime` have not changed
  their own public shape since M7.2/M7.3 to accommodate any of Research,
  Outreach, or (when built) Reply Intelligence/Supervisor's own Agents.
- **Cost/capability/tier metadata is read by the Gateway, never by a
  domain.** No domain-level code reads `PROVIDER_TIER_REGISTRY`,
  `ProviderCapabilities`, or the price tables directly — see Section 5
  for the one real piece of forward-looking cleanup this uniformity
  points toward.

## 5. Roadmap note — future architectural improvement only, NOT scheduled, NOT implemented

**Unified `ModelMetadata` registry.** Today, per-`(provider_key, model)`
facts are split across three parallel structures that each independently
mirror the same two-level "provider default + per-model override" shape:

- `app/ai_gateway/capabilities.py` — `ProviderCapabilities`
  (protocol-level, per provider_key) + `_CAPABILITY_OVERRIDES`
  (per-model overrides for `max_context_tokens`/`max_output_tokens`/
  `reasoning_support`).
- `app/ai_gateway/accounting.py` — `_PROVIDER_DEFAULT_PRICE_USD_PER_1K`
  (per provider_key) + `_MODEL_PRICE_OVERRIDES_USD_PER_1K` (per-model
  overrides).
- `app/ai_gateway/tiers.py` — `PROVIDER_TIER_REGISTRY` (per provider_key
  only, no per-model dimension today).
- Each concrete `ProviderClient`'s own `default_model` property
  (`app/ai_gateway/providers/*_client.py`).

Consolidating capabilities + pricing + tier + context/output limits +
reasoning level + default model into one authoritative
`(provider_key, model | None)`-keyed `ModelMetadata` structure would
remove this duplication and give a future cost-aware or
capability-aware policy engine one place to read instead of three. This
is recorded here as a real, worthwhile future direction — **not**
scoped, not scheduled, and explicitly not to be built as part of closing
out v1. The current three-registry shape works correctly today and
should not be refactored until a concrete milestone actually needs the
consolidation (the same "extend as real usage accumulates, not
speculatively ahead of it" discipline every registry in this codebase
already follows).

## 6. Summary

Provider-Neutral AI Gateway v1 (M-AIGW-1 through M-AIGW-5) is complete.
Two domains (Research, Outreach) are real, shipped Gateway consumers
with deliberately different response shapes, proving the abstraction
generalizes. Two more (Personalization, Reply Intelligence) are
scoped-but-not-started future work, at different seam-readiness levels
(Reply Intelligence's registry already exists; Personalization's does
not). Multi-Agent orchestration (Supervisor) is real, working
infrastructure with zero concrete plans registered — ready the moment a
first multi-agent workflow is approved. No further Gateway-core work is
implied by any of this; each future domain's own adoption is its own
future milestone, scoped and approved individually, exactly as
Research's and Outreach's were.
