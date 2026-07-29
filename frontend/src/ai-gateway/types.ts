/**
 * AI Gateway UI Foundation — M8.1 (AI Gateway) domain types.
 *
 * These types are the frontend's own contract for the AI Gateway UI zone.
 * They are deliberately NOT copied from any backend schema yet - there is
 * no backend integration in this milestone (see
 * docs/architecture/ai-gateway-ui-ux-architecture.md and the approved M8.1
 * scope). Field names were chosen to plausibly match what a future
 * `ApiGatewayProvider` would map from the real AI Gateway backend
 * (app/ai_gateway/*, app/ai_workforce/*), so that swapping the provider
 * implementation later (see providers/GatewayDataProvider.ts) does not
 * require reshaping every hook/component that already consumes these
 * shapes - only the provider implementation changes.
 */

export type ProviderTier = "local" | "free" | "premium";

export type ProviderKey = "local_ollama" | "groq" | "gemini_ai_studio" | "gemini" | "claude" | "openai";

export type ConnectionStatus = "connected" | "not_configured" | "degraded" | "down";

export interface ProviderSummary {
  key: ProviderKey;
  label: string;
  tier: ProviderTier;
  status: ConnectionStatus;
  defaultModel: string | null;
  costPer1kInputUsd: number | null;
  costPer1kOutputUsd: number | null;
  avgLatencyMs: number | null;
  requestsToday: number;
  capabilities: string[];
}

export type GatewayHealthState = "healthy" | "degraded" | "down";

export interface GatewayOverview {
  gatewayHealth: GatewayHealthState;
  activeProviders: number;
  totalProviders: number;
  runningAgents: number;
  requestsToday: number;
  successRatePct: number;
  estimatedCostTodayUsd: number;
  premiumRequestsToday: number;
}

export type ActivityStatus = "success" | "waiting" | "failed";

export interface ActivityLogEntry {
  id: string;
  timestamp: string;
  feature: string;
  agent: string;
  capability: string;
  providerKey: ProviderKey | null;
  model: string | null;
  costUsd: number | null;
  latencyMs: number | null;
  status: ActivityStatus;
  companyName: string | null;
  chainSummary: string;
  errorMessage: string | null;
}

/**
 * `status` — M8.3 Step 7 (Premium Approval UI) addition. Mirrors backend
 * `ApprovalRequestRead.status` field-for-field (see that schema's own
 * docstring for the full semantics): whether an admin has already acted
 * on the (company, capability) pair this flagged event belongs to.
 * "approved" — a LIVE, non-expired pre-authorization exists right now.
 * "rejected" — the most recent decision for that pair was a rejection, or
 * an earlier approval has since expired with no later action.
 * "pending" — no decision recorded yet, or the most recent one expired
 * (an expired approval correctly reads as pending again).
 */
export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface ApprovalRequest {
  id: string;
  status: ApprovalStatus;
  feature: string;
  reason: string;
  providerKey: ProviderKey;
  model: string;
  estimatedCostUsd: number;
  requestedAt: string;
  waitingMinutes: number;
  companyName: string | null;
}

/**
 * PremiumPreauthorization — M8.3 Step 7 (Premium Approval UI) addition.
 * Mirrors backend/app/schemas/ai_gateway.py's PremiumPreauthorizationRead
 * field-for-field. Returned by both `approveRequest()`/`rejectRequest()`
 * (the row just written) and `listApprovalHistory()` (every past decision,
 * most recent first) — see GatewayDataProvider.ts's own docstring for each
 * method. This grants/records a PRE-AUTHORIZATION for the flagged event's
 * own (company, capability) pair, NOT a resume of that specific request —
 * there is nothing to resume (see ApprovalRequest's own "past EVENT, not a
 * live blocking queue" framing above; the same honesty applies here).
 * `decision` is `DECISION_APPROVED`/`DECISION_REJECTED`, never "pending" —
 * a history row IS a decision, by definition.
 */
export interface PremiumPreauthorization {
  id: string;
  companyName: string | null;
  capability: string;
  feature: string;
  decision: "approved" | "rejected";
  decidedBy: string | null;
  decidedAt: string;
  expiresAt: string | null;
  sourceReason: string | null;
  sourceEstimatedCostUsd: number | null;
}

export type RoutingNodeState = "skipped" | "passed" | "terminal-success" | "terminal-waiting" | "terminal-failed";

export interface RoutingNode {
  id: string;
  label: string;
  state: RoutingNodeState;
  detail?: string;
}

export interface RoutingDecision {
  id: string;
  capability: string;
  timestamp: string;
  nodes: RoutingNode[];
  outcome: ActivityStatus;
}

/**
 * GatewaySettings — M8.2 (AI Gateway Backend Integration) addition. Read
 * only, mirrors the real `GET /ai-gateway/settings` response
 * (backend/app/schemas/ai_gateway.py's GatewaySettingsRead) - a live
 * projection of app.core.config.settings / app.ai_gateway.router /
 * app.ai_gateway.local_model_policy, never a second editable copy.
 * Settings persistence (a PUT to change any of this) is out of scope for
 * M8.2 - see AIGatewaySettings.tsx's own docstring.
 */
export interface GatewaySettings {
  aiMode: string;
  requirePremiumApproval: boolean;
  maxAttemptsPerProvider: number;
  defaultTimeoutSeconds: number;
  capabilityProviderPreference: Record<string, string[]>;
  localModelRoles: Record<string, string | null>;
  capabilityLocalModelRole: Record<string, string[]>;
}

/**
 * ProviderConfig / ProviderConfigWrite / ProviderConfigAuditEntry /
 * ConnectionTestResult — M8.3 Step 2 (AI Gateway Management & Control,
 * Provider Management) additions. Mirror
 * backend/app/schemas/ai_gateway.py's ProviderConfigRead/
 * ProviderConfigWrite/AIProviderConfigAuditRead/ConnectionTestResultRead
 * field-for-field (camelCase here, snake_case there - see
 * ApiGatewayProvider.ts for the translation layer, same convention every
 * other type in this file already follows).
 *
 * `ProviderConfig` is the override ROW itself - the DB-backed value an
 * operator has (or hasn't) saved - distinct from `ProviderSummary` (the
 * EFFECTIVE, resolved value the AI Gateway actually uses right now, merged
 * with `.env` fallback). `hasApiKey` is the only signal about credential
 * state this app ever receives; the real key is never returned by any
 * read.
 */
export interface ProviderConfig {
  providerKey: ProviderKey;
  enabled: boolean;
  hasApiKey: boolean;
  baseUrl: string | null;
  defaultModel: string | null;
  extraSettings: Record<string, unknown>;
  updatedAt: string | null;
  updatedByUserEmail: string | null;
}

/**
 * Every field left `undefined` means "leave this field alone" - the
 * `clear*` flags exist because `undefined`/empty-string is itself
 * ambiguous for api_key/base_url/default_model (see the backend
 * `ProviderConfigWrite` schema's own docstring for why).
 */
export interface ProviderConfigWrite {
  enabled?: boolean;
  apiKey?: string;
  clearApiKey?: boolean;
  baseUrl?: string;
  clearBaseUrl?: boolean;
  defaultModel?: string;
  clearDefaultModel?: boolean;
  extraSettings?: Record<string, unknown>;
}

export interface ProviderConfigAuditEntry {
  id: string;
  providerKey: ProviderKey;
  changedAt: string;
  changedByUserEmail: string | null;
  fieldChanges: Record<string, { old: unknown; new: unknown }>;
}

export interface ConnectionTestResult {
  providerKey: ProviderKey;
  success: boolean;
  message: string;
  latencyMs: number | null;
  availableModels: string[] | null;
}

/**
 * ModelRole / ModelRoleWrite — M8.3 Step 3 (AI Gateway Management &
 * Control, Model Role Management) additions. Mirror
 * backend/app/schemas/ai_gateway.py's ModelRoleRead/ModelRoleWrite
 * field-for-field. Per CEO decision #2 (local-tier only), a "role"
 * assigns a MODEL to a SEMANTIC ROLE NAME consumed exclusively by
 * `LocalOllamaProviderClient._resolve_model()` - it never affects which
 * PROVIDER (local/free/premium) a capability routes to, and it never
 * touches Claude/OpenAI/Gemini/Groq. See `GatewaySettings.capabilityLocalModelRole`
 * for the (still code-level, read-only) capability -> role preference
 * order - this type is only the role -> model assignment half.
 *
 * Unlike `ProviderConfig`, there is no fixed universe of role names to
 * synthesize a placeholder for - `GET /ai-gateway/model-roles` returns
 * only roles that actually have a saved row; creating a role with a new
 * name IS how a new semantic role (e.g. "coding") gets added.
 */
export interface ModelRole {
  roleName: string;
  model: string;
  enabled: boolean;
  updatedAt: string | null;
  updatedByUserEmail: string | null;
}

export interface ModelRoleWrite {
  model?: string;
  enabled?: boolean;
}

/**
 * RoutingSimulation* — M8.3 Step 4 (AI Gateway Management & Control,
 * Routing Simulator) additions. Mirror
 * backend/app/schemas/ai_gateway.py's RoutingSimulationRequest/
 * RoutingSimulationNodeRead/RoutingSimulationRead field-for-field.
 *
 * READ-ONLY end to end: `simulateRouting()` (see GatewayDataProvider.ts)
 * never mutates any setting and never attempts a real provider call -
 * `aiModeOverride`/`providerEnabledOverrides` are purely hypothetical
 * inputs to a pure backend computation, never persisted. This is
 * intentionally a DIFFERENT, richer node shape than `RoutingNode` above
 * (which only ever replays a PAST/live decision with five generic
 * states) - the simulator shows the FULL candidate chain (including
 * providers that would never be reached) with a distinct state per
 * candidate and a human-readable reason, per the CEO's own Step 4
 * requirements.
 */
export type RoutingSimulationRole = "primary" | "fallback" | "premium";

export type RoutingSimulationNodeState =
  | "would_call"
  | "requires_approval"
  | "skipped_not_configured"
  | "skipped_capability_mismatch"
  | "skipped_not_reached";

export interface RoutingSimulationNode {
  providerKey: string;
  label: string;
  tier: ProviderTier;
  role: RoutingSimulationRole;
  position: number;
  state: RoutingSimulationNodeState;
  reason: string;
  configured: boolean;
  overridden: boolean;
  costPer1kInputUsd: number | null;
  costPer1kOutputUsd: number | null;
  estimatedCostUsd: number | null;
}

export interface RoutingSimulationRequestInput {
  capability: string;
  aiModeOverride?: string;
  providerEnabledOverrides?: Record<string, boolean>;
}

export interface RoutingSimulationResult {
  capability: string;
  featureLabel: string;
  aiModeUsed: string;
  requestedCapabilities: string[];
  capabilityExcluded: string[];
  nodes: RoutingSimulationNode[];
  outcome: ActivityStatus;
  outcomeDetail: string;
}

/**
 * CapabilityValues / ProviderCapability — M8.3 Step 5 (AI Gateway
 * Management & Control, Provider Capability Viewer). Mirror
 * backend/app/schemas/ai_gateway.py's CapabilityValuesRead/
 * ProviderCapabilityRead field-for-field.
 *
 * Two-level granularity, matching app/ai_gateway/capabilities.py's own
 * design (see that module's docstring): `providerLevel` is the fixed,
 * protocol-level fact about a provider's SDK/wire-format integration
 * (declared once per `ProviderClient` subclass); `effective` is the same
 * shape resolved for that provider's CURRENTLY CONFIGURED default model -
 * identical to `providerLevel` unless a real per-model override has been
 * registered for that model (`hasModelOverride`/`overriddenFields` make
 * this distinction explicit rather than leaving a caller to diff the two
 * objects itself). `maxContextTokens`/`maxOutputTokens` are informational
 * per-model numbers (not a supported/unsupported boolean) - `null` means
 * "not declared," never "zero."
 *
 * Today, with zero real entries in `_CAPABILITY_OVERRIDES`, every provider
 * in this app honestly reports `hasModelOverride: false` and
 * `providerLevel` === `effective` - this type exists so the UI can keep
 * telling that truth instead of fabricating a difference, while already
 * being ready to show one the moment a real per-model override is
 * registered.
 */
export interface CapabilityValues {
  structuredOutput: boolean;
  toolCalling: boolean;
  streaming: boolean;
  vision: boolean;
  embeddings: boolean;
  reasoningSupport: boolean;
  maxContextTokens: number | null;
  maxOutputTokens: number | null;
}

export interface ProviderCapability {
  providerKey: string;
  label: string;
  tier: ProviderTier;
  defaultModel: string | null;
  providerLevel: CapabilityValues;
  effective: CapabilityValues;
  hasModelOverride: boolean;
  overriddenFields: string[];
}

/**
 * DiagnosticFinding / GatewayDiagnostics — M8.3 Step 6 (AI Gateway
 * Management & Control, Gateway Diagnostics). Mirror
 * backend/app/schemas/ai_gateway.py's DiagnosticFindingRead/
 * GatewayDiagnosticsRead field-for-field.
 *
 * READ-ONLY end to end: `GET /ai-gateway/diagnostics` never mutates
 * anything and there is no action to take against a finding here (same
 * "nothing to action against" shape `ApprovalRequest`'s own docstring
 * already established for Approvals). `severity` is the CEO's own
 * "clearly separate warnings from errors" requirement made explicit -
 * `"error"` (something is currently broken), `"warning"` (a real risk or
 * silent gap), `"info"` (worth knowing, not a problem) - see
 * `app.ai_gateway.diagnostics`'s own docstring for the full rationale
 * behind each. `providerKey`/`capability` are `null` for a finding that
 * isn't about one specific provider/capability.
 */
export type DiagnosticSeverity = "error" | "warning" | "info";

export interface DiagnosticFinding {
  category: string;
  severity: DiagnosticSeverity;
  title: string;
  detail: string;
  recommendation: string;
  providerKey: string | null;
  capability: string | null;
}

export interface GatewayDiagnostics {
  generatedAt: string;
  findings: DiagnosticFinding[];
  errorCount: number;
  warningCount: number;
  infoCount: number;
}
