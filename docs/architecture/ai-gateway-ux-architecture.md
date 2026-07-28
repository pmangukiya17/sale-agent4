# AI Gateway UI Architecture (M8.1 — UI Foundation, M8.2 — Backend Integration)

Status: **Approved** (CEO, 2026-07-26 for M8.1; 2026-07-28 for M8.2). This
document is the source of truth for the AI Gateway UI Foundation
milestone (M8.1) and the AI Gateway Backend Integration milestone (M8.2),
and for the sections referenced by docstrings throughout
`frontend/src/ai-gateway/`, `frontend/src/pages/ai-gateway/`,
`frontend/src/design-system/SlideOver.tsx`, `backend/app/ai_gateway/`, and
`backend/app/api/routes/ai_gateway.py`.

See Section 10 for the M8.2 addendum (real backend, `ApiGatewayProvider`,
and task-based local model routing). Sections 0-9 below are the original
M8.1 UI-foundation design and remain accurate for the UI architecture
itself, which M8.2 deliberately left intact.

It reflects `docs/architecture/provider-neutral-ai-gateway-plan.md` (the
backend provider/routing/policy engine, M-AIGW-1..5, already implemented)
projected onto a new top-level UI zone. M8.1 builds ONLY the UI
foundation — layout, routes, reusable components, and a mock data layer.
No backend integration, charts, live updates, provider configuration,
approval-workflow execution, or settings persistence are in scope. See
Section 9 for the full deferred list.

## 0. Governing principle: honesty over fabrication

Every page and component in this zone either (a) renders real data from
the mock provider abstraction (Section 8), reflecting what the backend
plan actually produces (`RoutingDecision`, `ProviderClient.default_model`,
the cost price table from M-AIGW-4, etc.), or (b) renders an explicit
`PlaceholderNotice` stating what is not yet implemented and why. Nothing
in this milestone fabricates data, animates a fake "live" state, or
implies a capability (charts, settings persistence, approval execution)
that does not exist yet. `RoutingChainVisualizer` is the clearest
instance of this: it replays one real mock `RoutingDecision`, never a
generic marketing diagram of gateway capability.

## 1. Information architecture

AI Gateway is its own top-level sidebar zone, deliberately separate from
"AI Workforce":

- **AI Workforce** — company-scoped: what the AI is doing for one
  business right now (agents, execution traces). Gated by
  `activeCompanyId`/`requiresCompany`, same as every other
  `/businesses/:companyId/...` zone.
- **AI Gateway** — workspace-scoped: how the provider-neutral routing,
  cost, and approval infrastructure underneath is working, across every
  business. No `requiresCompany` gate on any item in this zone.

Sidebar order places AI Gateway immediately after AI Workforce (see
`navConfig.ts`), reflecting that it is infrastructure supporting every
company-scoped AI feature above it. No dynamic badge on "Approvals" in
this milestone — `NavItem.badge` is a static string; a live pending-count
pill is deferred until this zone has a real backend to subscribe to.

## 2. Routes

| Path | Page | Notes |
|---|---|---|
| `/ai-gateway` | Overview | index route |
| `/ai-gateway/providers` | Providers | grid of all 6 registered providers |
| `/ai-gateway/providers/:providerKey` | Provider Detail | drill-down, not its own nav item |
| `/ai-gateway/routing` | Routing | last routing decision per capability |
| `/ai-gateway/activity` | Activity | full request log |
| `/ai-gateway/usage` | Usage & Cost | cost/token aggregates |
| `/ai-gateway/approvals` | Approvals | pending premium-approval queue |
| `/ai-gateway/health` | Health | provider health + capability matrix |
| `/ai-gateway/settings` | Settings | shell only, not yet implemented |

All nine routes are nested under one parent `<Route path="/ai-gateway" element={<AIGatewayLayout/>}>` in `App.tsx`, mirroring `DeliveryLayout`'s
nested-route shape. `providers/:providerKey` is a child route (not a
sibling) so it renders inside the same layout shell; `pageMeta.ts`'s
prefix-match fallback keeps "Providers" highlighted in the page-nav strip
while on a provider's detail page.

## 3. AIGatewayLayout

Follows `DeliveryLayout`'s philosophy (breadcrumb + heading + a routed
cross-page nav strip + `<Outlet/>`), not its exact shape. `DeliveryLayout`'s
three tabs are three views of one concept ("Delivery"), so one static
title covers all of them. AI Gateway's 8 destinations are each their own
distinct page, so `AIGatewayLayout` derives title/subtitle from the
current route via `pageMeta.ts`'s shared `AI_GATEWAY_PAGES` config. Uses
hand-rolled `NavLink`s for the page strip, not the design-system `Tabs`
primitive, for the same reason `DeliveryLayout` does: these are real
routes with real URLs, and `Tabs` is deliberately state-only. Mounts
`GatewayDataProviderProvider` here (not in `main.tsx`) so the mock data
layer is scoped to this route subtree only.

## 4. Pages

### 4.1 Overview (`/ai-gateway`)
7 KPI tiles (Gateway Health, Active/Total Providers, Running Agents,
Today's Requests, Success Rate, Est. Cost Today, Premium Requests) via the
existing `KpiCard`, a Recent Activity preview (top 5), a Pending Premium
Approvals preview (top 2), and two `PlaceholderNotice`s for the Provider
Mix and Cost Trend charts (Section 9).

### 4.2 Providers (`/ai-gateway/providers`)
Grid of `ProviderCard` for all 6 providers in the mock registry
(`local_ollama`, `groq`, `gemini_ai_studio`, `gemini`, `claude`, `openai`),
mirroring the real `PROVIDER_CLIENT_REGISTRY` from the backend plan. The
set is fixed and known, so there is no "empty" case beyond loading.

### 4.3 Provider Detail (`/ai-gateway/providers/:providerKey`)
One summary card (status, tier, default model, cost/1k tokens, avg
latency, capabilities) plus one `PlaceholderNotice` covering the fuller
6-tab layout (Connection / Capabilities / Models & Pricing / Usage /
Failures / Configuration) that a future milestone would build once
provider configuration and usage history exist.

### 4.4 Routing (`/ai-gateway/routing`)
Replays the last real (mock) `RoutingDecision` per capability using
`RoutingChainVisualizer` — see Section 0's honesty principle. One card
per capability, each showing its node chain in order.

### 4.5 Activity (`/ai-gateway/activity`)
Reuses `Table` unmodified. Row click opens `ActivityDetailDrawer`
(`SlideOver`) rather than navigating, keeping the log scannable.

### 4.6 Usage & Cost (`/ai-gateway/usage`)
Three KPIs computed client-side from the same mock activity log Activity
already uses (no new fixture). Chart area (daily/monthly cost, provider
distribution) is one `PlaceholderNotice` — see Section 9 for the
recommended charting approach when this is built.

### 4.7 Approvals (`/ai-gateway/approvals`)
Grid of `ApprovalCard` for the full pending queue. Approve/Reject are
wired to a `Toast` ("not yet implemented") rather than either faking
success or disabling the buttons — approval-workflow execution is
explicitly out of scope. History is one `PlaceholderNotice`.

### 4.8 Health (`/ai-gateway/health`)
Per-provider connection status list + `CapabilityMatrix`. Failover
events, routing statistics, and diagnostics warnings all depend on
live/backend signals this milestone doesn't have, so they render as one
`PlaceholderNotice` rather than fabricated rows.

### 4.9 Settings (`/ai-gateway/settings`)
Deliberate shell: one `PlaceholderNotice`. Routing mode, provider
priority, default models, and cost limits are designed here in principle
but settings persistence is out of scope for this milestone — no
half-wired form whose Save button does nothing.

## 5. Reusable components

| Component | Purpose | Depends on | Future reuse |
|---|---|---|---|
| `ProviderIdentity` (`identity/providerIdentity.ts`) | Single source of truth for each provider's label/tier/accent/icon/dot color | `Card`'s `AccentColor` | Any future provider-facing UI (Settings' provider-priority list, billing) |
| `ProviderCard` | Provider grid tile: identity + status + tier + capabilities | `ProviderIdentity`, `TierBadge`, `CostPill`, `StatusIndicator`, `Card` | Settings zone provider list |
| `TierBadge` | local/free/premium tier pill | `Badge` | Anywhere a provider's cost tier needs a compact label |
| `ProviderChip` | Inline provider reference (Activity rows, drawers) | `ProviderIdentity` | Any table/list row referencing a provider |
| `CostPill` | Formats a USD amount with tier-aware coloring | `ProviderIdentity` tiers | Usage & Cost, Provider Detail, any cost-bearing row |
| `ApprovalCard` | One pending premium-approval request | `Card`, `ProviderChip`, `CostPill`, `Button` | Approval history (once built), Overview preview |
| `RoutingChainVisualizer` | Renders one real `RoutingDecision.nodes` chain | `RoutingNode` type | Activity drawer (future: per-request chain), Provider Detail |
| `CapabilityMatrix` | Provider × capability grid | `ProviderIdentity` | Provider Detail's future "Capabilities" tab |
| `ActivityDetailDrawer` | Read-only inspector for one activity row | `SlideOver`, `ProviderChip`, `CostPill`, `StatusIndicator` | Any future per-request detail view |

## 6. SlideOver primitive

`frontend/src/design-system/SlideOver.tsx` — a new, standalone
right-edge inspector primitive (portal, Escape support, backdrop, focus
management), reusing `Modal`'s internal patterns but not extending
`Modal` itself: `Modal` is a centered, blocking confirmation/form
surface; a right-edge inspector needs different entrance motion,
different sizing, and a different mental model (a peek at record detail
you can dismiss without losing your place in an underlying list), not a
`placement` prop bolted onto `Modal`. `ActivityDetailDrawer` is the first
real consumer.

## 7. Visual language

### 7.1 Provider identity
Each provider has one fixed accent (`local_ollama`=emerald, `groq`=teal,
`gemini_ai_studio`=cyan, `gemini`=indigo, `claude`=gold, `openai`=royal-blue)
and icon, defined once in `providerIdentity.ts` and reused everywhere a
provider appears (chip, card, matrix, detail page) — one accent per
provider, no re-derivation.

### 7.2 Approval urgency
`ApprovalCard` uses `accent="amber"` as the one place in this zone amber
is used as a card's ambient identity rather than only a `Badge`/status
tone, deliberately, so pending approvals visually stand apart from the
calm blues/greens/violets everywhere else in the AI Gateway pages.
`active` is intentionally always true on `ApprovalCard` — a pending
approval is inherently "live" for its entire time on screen, a real,
always-true signal, not a fabricated one.

## 8. Mock data provider architecture

```
GatewayDataProvider (interface)
        ↑ implements
MockGatewayProvider (this milestone)
        ↑ future implementation
ApiGatewayProvider (future — real backend calls)
```

`GatewayDataProviderContext` supplies the active provider instance
(`MockGatewayProvider` today) to the hook layer via React context, scoped
to the `/ai-gateway` route subtree by `AIGatewayLayout`. Hooks
(`useProviders`, `useGatewayOverview`, `useActivity`, `useApprovals`,
`useRouting`) never read fixtures directly — they call the interface
through the context, and each returns the project's standard contract:
`{ data, isLoading, error, refresh }`. `MockGatewayProvider` uses
realistic asynchronous delays (not synchronous fake-instant resolution)
so loading states are exercised honestly. Swapping to
`ApiGatewayProvider` later requires no hook or page changes — only a new
provider implementation and a context value swap.

## 9. Explicitly deferred (not in this milestone)

Charts (no Recharts or any charting library installed/approved this
pass — recommended approach when built: Recharts, consistent with
`recharts` already being an approved artifact-library dependency
elsewhere in the design system's tooling notes), live updates / polling /
WebSockets, backend API integration (all data is mock), provider
configuration (connecting/editing a provider's credentials), approval
workflow execution (Approve/Reject are inert, toast-only), settings
persistence, dynamic navigation badges (e.g. a live Approvals pending
count), and any changes to AI Workforce.

## 10. M8.2 addendum — Backend Integration + task-based local model routing

Approved 2026-07-28. Replaces `MockGatewayProvider` with a real
`ApiGatewayProvider` calling new, read-only `/ai-gateway/*` endpoints, and
adds capability-aware local model selection. The M8.1 UI architecture
(Sections 1-9 above) is unchanged — every page, hook signature, and
component from M8.1 still stands; this section only adds a real data
source underneath it and one new page's real content (Settings).

### 10.1 What was actually queryable vs. what M8.2 had to add

Research at the start of M8.2 found that `app/ai_gateway/` (M7.2/M11/
M-AIGW-1..5) had real routing/tier/capability/cost logic but **no
persisted history at all** — `log_ai_request()` only wrote a structured
log line (`app/ai_gateway/request_log.py`'s own docstring: "Deliberately
NOT a new database table this phase... A future migration can add an
ai_request_logs table"). There was also no durable "pending approval"
queue — the premium-approval gate (`PremiumApprovalRequiredError`) is a
synchronous pre-flight check, not a resumable workflow. M8.2 therefore:

- Added exactly one new table, `ai_request_logs`
  (`app/models/ai_request_log.py`, migration `0029`), and extended
  `log_ai_request()`'s body (not its signature or call sites) to also
  insert a row, via its own short-lived DB session, best-effort
  (failures are logged, never raised — observability must never break a
  real Gateway call).
- Built Activity/Approvals/Overview/Usage entirely from that new table.
- Built Providers/Health entirely from the *existing*, already-real
  `PROVIDER_CLIENT_REGISTRY`/`tiers`/`capabilities` — no DB needed.
- Built Routing as a **real-time policy preview** (calls
  `ProviderRouter.select()` fresh, for the two capabilities with live
  Gateway traffic today — `research_analysis`, `outreach_email_generation`)
  rather than a replay of history, since no full per-request routing
  chain is ever persisted (only a final outcome per attempt sequence).
- Built Settings as a live, read-only projection of
  `app.core.config.settings` / `CAPABILITY_PROVIDER_PREFERENCE` /
  `local_model_policy`'s tables — no persistence.
- Left Approvals read-only per the approved scope: it now shows real
  *past* premium-approval-required events from `ai_request_logs`, not a
  live actionable queue (none exists in this codebase to act against).

### 10.2 Task-based local model routing

`app/ai_gateway/local_model_policy.py` (new) is the single centralized
place a capability's semantic role preference (e.g. `research_analysis`
→ `["research"]`, `outreach_email_generation` → `["writing", "research"]`)
resolves to a configured local model, via `LOCAL_MODEL_ROLES` (role name
→ settings attribute name — semantic, never positional
`"default"/"secondary"`, per the CEO's explicit refinement over the
original proposal). Only `LocalOllamaProviderClient` overrides the new
`_resolve_model()` hook on `OpenAICompatibleProviderClient` to consult
this policy; `GroqProviderClient`/every cloud provider client is
untouched. `ProviderRouter`/`RoutingDecision` remain completely unaware
this exists — provider-neutral routing (which provider_key) and
per-provider model selection (which model, once inside that provider)
stay cleanly separated, exactly as before this addition. Adding a future
role (`coding`/`vision`/`reasoning`/`embeddings`) or model (DeepSeek,
Mistral, Llama 4) is always two additive edits — a new
`LOCAL_MODEL_<NAME>_MODEL` setting and one new `LOCAL_MODEL_ROLES` entry —
never a change to `router.py`, `client.py`, `capabilities.py`, or any
other provider.

### 10.3 Isolation rule

Activity/Approvals/Overview are scoped to the calling user's own
companies (`CompanyProfile.owner_user_id`); a log row with no
`company_profile_id` (a capability that hasn't threaded that context yet)
is excluded from every user-scoped view — never shown to anyone.
Provider-level stats (`requests_today`/`avg_latency_ms` on
`ProviderSummary`) are the one deliberate exception, aggregated globally,
since provider credentials are instance-wide settings, not per-company
data.

### 10.4 Still not implemented (unchanged from Section 9, re-confirmed)

Provider configuration, settings persistence, approval actions, charts,
live updates, polling, WebSockets. Routing's "real-time preview" and
Approvals' "past events, not a live queue" framings above are the two
disclosed, necessary adaptations from M8.1's original mock-data framing —
both are consequences of what this codebase actually persists, not scope
cuts.
