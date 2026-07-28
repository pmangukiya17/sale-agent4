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

export interface ApprovalRequest {
  id: string;
  feature: string;
  reason: string;
  providerKey: ProviderKey;
  model: string;
  estimatedCostUsd: number;
  requestedAt: string;
  waitingMinutes: number;
  companyName: string | null;
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
