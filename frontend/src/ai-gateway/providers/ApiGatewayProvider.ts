import type { AxiosInstance } from "axios";
import type {
  ActivityLogEntry,
  ActivityStatus,
  ApprovalRequest,
  ConnectionTestResult,
  GatewayOverview,
  GatewaySettings,
  ModelRole,
  ModelRoleWrite,
  ProviderConfig,
  ProviderConfigAuditEntry,
  ProviderConfigWrite,
  ProviderKey,
  ProviderSummary,
  ProviderTier,
  RoutingDecision,
  RoutingNode,
} from "../types";
import type { GatewayDataProvider } from "./GatewayDataProvider";

/**
 * ApiGatewayProvider — M8.2 (AI Gateway Backend Integration). The real
 * `GatewayDataProvider` implementation, calling the new, read-only
 * `/ai-gateway/*` endpoints (app/api/routes/ai_gateway.py) via the
 * existing `apiClient` (api/client.ts) - same axios instance/JWT-interceptor
 * every other real hook in this app already uses (see
 * ai-workforce/useAgentActivities.ts for the precedent this follows).
 *
 * This class's ENTIRE job is translation: the backend returns snake_case
 * JSON (matching every other schema in this codebase - see
 * app/schemas/ai_gateway.py's own docstring for why it does NOT emit
 * camelCase), while every AI Gateway hook/component built in M8.1 depends
 * on the camelCase shapes in ../types.ts. Translating here - not by
 * changing types.ts, not by teaching the backend to emit camelCase - is
 * exactly why `GatewayDataProvider` exists as a seam: M8.1's hooks/pages/
 * components needed ZERO changes for this milestone.
 *
 * `getProvider()` maps a 404 (unknown provider_key) to `null`, matching
 * `MockGatewayProvider`'s own `?? null` contract - never lets a 404
 * propagate as a thrown error a hook wasn't written to catch.
 */
interface RawProviderSummary {
  key: string;
  label: string;
  tier: string;
  status: string;
  default_model: string | null;
  cost_per_1k_input_usd: number | null;
  cost_per_1k_output_usd: number | null;
  avg_latency_ms: number | null;
  requests_today: number;
  capabilities: string[];
}

interface RawGatewayOverview {
  gateway_health: string;
  active_providers: number;
  total_providers: number;
  running_agents: number;
  requests_today: number;
  success_rate_pct: number;
  estimated_cost_today_usd: number;
  premium_requests_today: number;
}

interface RawActivityLogEntry {
  id: string;
  timestamp: string;
  feature: string;
  agent: string;
  capability: string;
  provider_key: string | null;
  model: string | null;
  cost_usd: number | null;
  latency_ms: number | null;
  status: string;
  company_name: string | null;
  chain_summary: string;
  error_message: string | null;
}

interface RawApprovalRequest {
  id: string;
  feature: string;
  reason: string;
  provider_key: string;
  model: string;
  estimated_cost_usd: number;
  requested_at: string;
  waiting_minutes: number;
  company_name: string | null;
}

interface RawRoutingNode {
  id: string;
  label: string;
  state: string;
  detail?: string | null;
}

interface RawRoutingDecision {
  id: string;
  capability: string;
  timestamp: string;
  nodes: RawRoutingNode[];
  outcome: string;
}

interface RawGatewaySettings {
  ai_mode: string;
  require_premium_approval: boolean;
  max_attempts_per_provider: number;
  default_timeout_seconds: number;
  capability_provider_preference: Record<string, string[]>;
  local_model_roles: Record<string, string | null>;
  capability_local_model_role: Record<string, string[]>;
}

function toProviderSummary(raw: RawProviderSummary): ProviderSummary {
  return {
    key: raw.key as ProviderKey,
    label: raw.label,
    tier: raw.tier as ProviderTier,
    status: raw.status as ProviderSummary["status"],
    defaultModel: raw.default_model,
    costPer1kInputUsd: raw.cost_per_1k_input_usd,
    costPer1kOutputUsd: raw.cost_per_1k_output_usd,
    avgLatencyMs: raw.avg_latency_ms,
    requestsToday: raw.requests_today,
    capabilities: raw.capabilities,
  };
}

function toGatewayOverview(raw: RawGatewayOverview): GatewayOverview {
  return {
    gatewayHealth: raw.gateway_health as GatewayOverview["gatewayHealth"],
    activeProviders: raw.active_providers,
    totalProviders: raw.total_providers,
    runningAgents: raw.running_agents,
    requestsToday: raw.requests_today,
    successRatePct: raw.success_rate_pct,
    estimatedCostTodayUsd: raw.estimated_cost_today_usd,
    premiumRequestsToday: raw.premium_requests_today,
  };
}

function toActivityLogEntry(raw: RawActivityLogEntry): ActivityLogEntry {
  return {
    id: raw.id,
    timestamp: raw.timestamp,
    feature: raw.feature,
    agent: raw.agent,
    capability: raw.capability,
    providerKey: (raw.provider_key as ProviderKey | null) ?? null,
    model: raw.model,
    costUsd: raw.cost_usd,
    latencyMs: raw.latency_ms,
    status: raw.status as ActivityStatus,
    companyName: raw.company_name,
    chainSummary: raw.chain_summary,
    errorMessage: raw.error_message,
  };
}

function toApprovalRequest(raw: RawApprovalRequest): ApprovalRequest {
  return {
    id: raw.id,
    feature: raw.feature,
    reason: raw.reason,
    providerKey: raw.provider_key as ProviderKey,
    model: raw.model,
    estimatedCostUsd: raw.estimated_cost_usd,
    requestedAt: raw.requested_at,
    waitingMinutes: raw.waiting_minutes,
    companyName: raw.company_name,
  };
}

function toRoutingNode(raw: RawRoutingNode): RoutingNode {
  return {
    id: raw.id,
    label: raw.label,
    state: raw.state as RoutingNode["state"],
    detail: raw.detail ?? undefined,
  };
}

function toRoutingDecision(raw: RawRoutingDecision): RoutingDecision {
  return {
    id: raw.id,
    capability: raw.capability,
    timestamp: raw.timestamp,
    nodes: raw.nodes.map(toRoutingNode),
    outcome: raw.outcome as ActivityStatus,
  };
}

interface RawProviderConfig {
  provider_key: string;
  enabled: boolean;
  has_api_key: boolean;
  base_url: string | null;
  default_model: string | null;
  extra_settings: Record<string, unknown>;
  updated_at: string | null;
  updated_by_user_email: string | null;
}

interface RawProviderConfigAuditEntry {
  id: string;
  provider_key: string;
  changed_at: string;
  changed_by_user_email: string | null;
  field_changes: Record<string, { old: unknown; new: unknown }>;
}

interface RawConnectionTestResult {
  provider_key: string;
  success: boolean;
  message: string;
  latency_ms: number | null;
  available_models: string[] | null;
}

function toProviderConfig(raw: RawProviderConfig): ProviderConfig {
  return {
    providerKey: raw.provider_key as ProviderKey,
    enabled: raw.enabled,
    hasApiKey: raw.has_api_key,
    baseUrl: raw.base_url,
    defaultModel: raw.default_model,
    extraSettings: raw.extra_settings,
    updatedAt: raw.updated_at,
    updatedByUserEmail: raw.updated_by_user_email,
  };
}

function toProviderConfigAuditEntry(raw: RawProviderConfigAuditEntry): ProviderConfigAuditEntry {
  return {
    id: raw.id,
    providerKey: raw.provider_key as ProviderKey,
    changedAt: raw.changed_at,
    changedByUserEmail: raw.changed_by_user_email,
    fieldChanges: raw.field_changes,
  };
}

function toConnectionTestResult(raw: RawConnectionTestResult): ConnectionTestResult {
  return {
    providerKey: raw.provider_key as ProviderKey,
    success: raw.success,
    message: raw.message,
    latencyMs: raw.latency_ms,
    availableModels: raw.available_models,
  };
}

interface RawModelRole {
  role_name: string;
  model: string;
  enabled: boolean;
  updated_at: string | null;
  updated_by_user_email: string | null;
}

function toModelRole(raw: RawModelRole): ModelRole {
  return {
    roleName: raw.role_name,
    model: raw.model,
    enabled: raw.enabled,
    updatedAt: raw.updated_at,
    updatedByUserEmail: raw.updated_by_user_email,
  };
}

function toGatewaySettings(raw: RawGatewaySettings): GatewaySettings {
  return {
    aiMode: raw.ai_mode,
    requirePremiumApproval: raw.require_premium_approval,
    maxAttemptsPerProvider: raw.max_attempts_per_provider,
    defaultTimeoutSeconds: raw.default_timeout_seconds,
    capabilityProviderPreference: raw.capability_provider_preference,
    localModelRoles: raw.local_model_roles,
    capabilityLocalModelRole: raw.capability_local_model_role,
  };
}

export class ApiGatewayProvider implements GatewayDataProvider {
  constructor(private readonly http: AxiosInstance) {}

  async getOverview(): Promise<GatewayOverview> {
    const res = await this.http.get<RawGatewayOverview>("/ai-gateway/overview");
    return toGatewayOverview(res.data);
  }

  async listProviders(): Promise<ProviderSummary[]> {
    const res = await this.http.get<RawProviderSummary[]>("/ai-gateway/providers");
    return res.data.map(toProviderSummary);
  }

  async getProvider(key: ProviderKey): Promise<ProviderSummary | null> {
    try {
      const res = await this.http.get<RawProviderSummary>(`/ai-gateway/providers/${key}`);
      return toProviderSummary(res.data);
    } catch (error: unknown) {
      if (isNotFound(error)) return null;
      throw error;
    }
  }

  async listActivity(): Promise<ActivityLogEntry[]> {
    const res = await this.http.get<RawActivityLogEntry[]>("/ai-gateway/activity", { params: { limit: 100 } });
    return res.data.map(toActivityLogEntry);
  }

  async listApprovals(): Promise<ApprovalRequest[]> {
    const res = await this.http.get<RawApprovalRequest[]>("/ai-gateway/approvals", { params: { limit: 50 } });
    return res.data.map(toApprovalRequest);
  }

  async listRoutingDecisions(): Promise<RoutingDecision[]> {
    const res = await this.http.get<RawRoutingDecision[]>("/ai-gateway/routing");
    return res.data.map(toRoutingDecision);
  }

  async getSettings(): Promise<GatewaySettings> {
    const res = await this.http.get<RawGatewaySettings>("/ai-gateway/settings");
    return toGatewaySettings(res.data);
  }

  async getProviderConfig(key: ProviderKey): Promise<ProviderConfig | null> {
    try {
      const res = await this.http.get<RawProviderConfig>(`/ai-gateway/providers/${key}/config`);
      return toProviderConfig(res.data);
    } catch (error: unknown) {
      if (isNotFound(error)) return null;
      throw error;
    }
  }

  async saveProviderConfig(key: ProviderKey, patch: ProviderConfigWrite): Promise<ProviderConfig> {
    // camelCase -> snake_case, field-for-field mirroring
    // backend/app/schemas/ai_gateway.py's ProviderConfigWrite - every
    // field left `undefined` here is simply omitted from the body, which
    // axios/FastAPI/pydantic already treat as "not provided" (same as the
    // schema's own `None` default), so "leave alone" requires no special
    // handling on this side.
    const body = {
      enabled: patch.enabled,
      api_key: patch.apiKey,
      clear_api_key: patch.clearApiKey,
      base_url: patch.baseUrl,
      clear_base_url: patch.clearBaseUrl,
      default_model: patch.defaultModel,
      clear_default_model: patch.clearDefaultModel,
      extra_settings: patch.extraSettings,
    };
    const res = await this.http.put<RawProviderConfig>(`/ai-gateway/providers/${key}/config`, body);
    return toProviderConfig(res.data);
  }

  async listProviderConfigAudit(key: ProviderKey, limit = 20): Promise<ProviderConfigAuditEntry[]> {
    const res = await this.http.get<RawProviderConfigAuditEntry[]>(`/ai-gateway/providers/${key}/config/audit`, {
      params: { limit },
    });
    return res.data.map(toProviderConfigAuditEntry);
  }

  async testConnection(key: ProviderKey): Promise<ConnectionTestResult> {
    const res = await this.http.post<RawConnectionTestResult>(`/ai-gateway/providers/${key}/test-connection`);
    return toConnectionTestResult(res.data);
  }

  async listModelRoles(): Promise<ModelRole[]> {
    const res = await this.http.get<RawModelRole[]>("/ai-gateway/model-roles");
    return res.data.map(toModelRole);
  }

  async saveModelRole(roleName: string, patch: ModelRoleWrite): Promise<ModelRole> {
    const body = { model: patch.model, enabled: patch.enabled };
    const res = await this.http.put<RawModelRole>(`/ai-gateway/model-roles/${roleName}`, body);
    return toModelRole(res.data);
  }

  async deleteModelRole(roleName: string): Promise<void> {
    await this.http.delete(`/ai-gateway/model-roles/${roleName}`);
  }
}

function isNotFound(error: unknown): boolean {
  return Boolean(
    error && typeof error === "object" && "response" in error && (error as { response?: { status?: number } }).response?.status === 404
  );
}
