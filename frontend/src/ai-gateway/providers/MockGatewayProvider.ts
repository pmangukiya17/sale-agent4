import type {
  ActivityLogEntry,
  ApprovalRequest,
  ConnectionTestResult,
  GatewayOverview,
  GatewaySettings,
  ProviderConfig,
  ProviderConfigAuditEntry,
  ProviderConfigWrite,
  ProviderKey,
  ProviderSummary,
  RoutingDecision,
} from "../types";
import type { GatewayDataProvider } from "./GatewayDataProvider";

/**
 * MockGatewayProvider — the only `GatewayDataProvider` implementation in
 * this milestone (no backend integration approved yet). Fixtures are
 * deliberately internally consistent with each other (the same six
 * providers, the same tier/pricing facts the backend's real
 * `accounting.py`/`capabilities.py` already use, per
 * docs/architecture/provider-neutral-ai-gateway-plan.md) rather than
 * independently-invented numbers per method - e.g. the pending approvals
 * here are the same requests that appear "waiting" in the activity log
 * and terminate in "terminal-waiting" in the routing decisions, so a user
 * clicking between pages sees one coherent story, not three unrelated
 * demos.
 *
 * `delay()` simulates a real network round-trip so loading states
 * (`isLoading`) are exercised honestly during development instead of
 * resolving synchronously - see each hook in ../hooks for how this is
 * surfaced.
 */
function delay<T>(value: T, ms = 400): Promise<T> {
  return new Promise((resolve) => window.setTimeout(() => resolve(value), ms));
}

const PROVIDERS: ProviderSummary[] = [
  {
    key: "local_ollama",
    label: "Ollama",
    tier: "local",
    status: "connected",
    defaultModel: "llama3.1:8b",
    costPer1kInputUsd: 0,
    costPer1kOutputUsd: 0,
    avgLatencyMs: 340,
    requestsToday: 46,
    capabilities: ["structured_output", "tool_calling"],
  },
  {
    key: "groq",
    label: "Groq",
    tier: "free",
    status: "connected",
    defaultModel: "llama-3.3-70b-versatile",
    costPer1kInputUsd: 0.00059,
    costPer1kOutputUsd: 0.00079,
    avgLatencyMs: 180,
    requestsToday: 812,
    capabilities: ["structured_output", "tool_calling", "streaming"],
  },
  {
    key: "gemini_ai_studio",
    label: "Gemini AI Studio",
    tier: "free",
    status: "not_configured",
    defaultModel: null,
    costPer1kInputUsd: 0,
    costPer1kOutputUsd: 0,
    avgLatencyMs: null,
    requestsToday: 0,
    capabilities: ["structured_output", "vision"],
  },
  {
    key: "gemini",
    label: "Gemini",
    tier: "premium",
    status: "connected",
    defaultModel: "gemini-3.6-flash",
    costPer1kInputUsd: 0.002,
    costPer1kOutputUsd: 0.012,
    avgLatencyMs: 1400,
    requestsToday: 61,
    capabilities: ["structured_output", "tool_calling", "vision", "reasoning_support"],
  },
  {
    key: "claude",
    label: "Claude",
    tier: "premium",
    status: "connected",
    defaultModel: "claude-sonnet-4-5",
    costPer1kInputUsd: 0.003,
    costPer1kOutputUsd: 0.015,
    avgLatencyMs: 2100,
    requestsToday: 201,
    capabilities: ["structured_output", "tool_calling", "reasoning_support"],
  },
  {
    key: "openai",
    label: "OpenAI",
    tier: "premium",
    status: "not_configured",
    defaultModel: null,
    costPer1kInputUsd: 0.0025,
    costPer1kOutputUsd: 0.015,
    avgLatencyMs: null,
    requestsToday: 0,
    capabilities: ["structured_output", "tool_calling", "vision"],
  },
];

const OVERVIEW: GatewayOverview = {
  gatewayHealth: "healthy",
  activeProviders: PROVIDERS.filter((p) => p.status === "connected").length,
  totalProviders: PROVIDERS.length,
  runningAgents: 3,
  requestsToday: 182,
  successRatePct: 98.4,
  estimatedCostTodayUsd: 3.42,
  premiumRequestsToday: 24,
};

const ACTIVITY: ActivityLogEntry[] = [
  {
    id: "act-1",
    timestamp: "2026-07-26T12:04:00Z",
    feature: "Research",
    agent: "Research Agent",
    capability: "research_analysis",
    providerKey: "groq",
    model: "llama-3.3-70b-versatile",
    costUsd: 0,
    latencyMs: 187,
    status: "success",
    companyName: "Acme Textiles Ltd.",
    chainSummary: "local (skipped) → free (groq) ✓",
    errorMessage: null,
  },
  {
    id: "act-2",
    timestamp: "2026-07-26T12:03:00Z",
    feature: "Outreach",
    agent: "Outreach Agent",
    capability: "outreach_email_generation",
    providerKey: "claude",
    model: "claude-sonnet-4-5",
    costUsd: 0.014,
    latencyMs: 2300,
    status: "success",
    companyName: "Meridian Apparel Co.",
    chainSummary: "local (skipped) → free (skipped) → premium (claude) ✓",
    errorMessage: null,
  },
  {
    id: "act-3",
    timestamp: "2026-07-26T12:01:00Z",
    feature: "Outreach",
    agent: "Outreach Agent",
    capability: "outreach_email_generation",
    providerKey: "claude",
    model: "claude-sonnet-4-5",
    costUsd: null,
    latencyMs: null,
    status: "waiting",
    companyName: "Northgate Exports",
    chainSummary: "local (skipped) → free (skipped) → premium (claude) — waiting for approval",
    errorMessage: null,
  },
  {
    id: "act-4",
    timestamp: "2026-07-26T11:58:00Z",
    feature: "Research",
    agent: "Research Agent",
    capability: "research_analysis",
    providerKey: "groq",
    model: "llama-3.3-70b-versatile",
    costUsd: 0,
    latencyMs: 165,
    status: "success",
    companyName: "Acme Textiles Ltd.",
    chainSummary: "local (skipped) → free (groq) ✓",
    errorMessage: null,
  },
  {
    id: "act-5",
    timestamp: "2026-07-26T11:52:00Z",
    feature: "Research",
    agent: "Research Agent",
    capability: "research_analysis",
    providerKey: null,
    model: null,
    costUsd: null,
    latencyMs: 4100,
    status: "failed",
    companyName: "Blue Harbor Freight",
    chainSummary: "local (skipped) → free (groq) timeout, 2 retries → exhausted",
    errorMessage: "Provider timeout after 2 retries.",
  },
  {
    id: "act-6",
    timestamp: "2026-07-26T11:47:00Z",
    feature: "Research",
    agent: "Research Agent",
    capability: "research_analysis",
    providerKey: "groq",
    model: "llama-3.3-70b-versatile",
    costUsd: 0,
    latencyMs: 201,
    status: "success",
    companyName: "Northgate Exports",
    chainSummary: "local (skipped) → free (groq) ✓",
    errorMessage: null,
  },
  {
    id: "act-7",
    timestamp: "2026-07-26T11:40:00Z",
    feature: "Outreach",
    agent: "Outreach Agent",
    capability: "outreach_email_generation",
    providerKey: "claude",
    model: "claude-sonnet-4-5",
    costUsd: 0.021,
    latencyMs: 1980,
    status: "success",
    companyName: "Acme Textiles Ltd.",
    chainSummary: "local (skipped) → free (skipped) → premium (claude) ✓",
    errorMessage: null,
  },
];

const APPROVALS: ApprovalRequest[] = [
  {
    id: "appr-1",
    feature: "Outreach · Email draft generation",
    reason: "Local and free providers are unavailable for this capability.",
    providerKey: "claude",
    model: "claude-sonnet-4-5",
    estimatedCostUsd: 0.014,
    requestedAt: "2026-07-26T12:01:00Z",
    waitingMinutes: 4,
    companyName: "Northgate Exports",
  },
  {
    id: "appr-2",
    feature: "Research · Company analysis",
    reason: "Free-tier confidence below threshold; escalated to premium.",
    providerKey: "claude",
    model: "claude-sonnet-4-5",
    estimatedCostUsd: 0.021,
    requestedAt: "2026-07-26T11:56:00Z",
    waitingMinutes: 9,
    companyName: "Blue Harbor Freight",
  },
];

const ROUTING_DECISIONS: RoutingDecision[] = [
  {
    id: "route-1",
    capability: "research_analysis",
    timestamp: "2026-07-26T12:04:00Z",
    outcome: "success",
    nodes: [
      { id: "n1", label: "Request received", state: "passed" },
      { id: "n2", label: "Capability check", state: "passed" },
      { id: "n3", label: "Local (Ollama)", state: "skipped", detail: "Capability not supported by local tier." },
      { id: "n4", label: "Free (Groq)", state: "terminal-success", detail: "187ms · $0.0000" },
    ],
  },
  {
    id: "route-2",
    capability: "outreach_email_generation",
    timestamp: "2026-07-26T12:01:00Z",
    outcome: "waiting",
    nodes: [
      { id: "n1", label: "Request received", state: "passed" },
      { id: "n2", label: "Capability check", state: "passed" },
      { id: "n3", label: "Local (Ollama)", state: "skipped", detail: "Capability not supported by local tier." },
      { id: "n4", label: "Free (Groq / Gemini AI Studio)", state: "skipped", detail: "Not configured / unavailable." },
      { id: "n5", label: "Premium (Claude)", state: "terminal-waiting", detail: "Waiting for approval · est. $0.014" },
    ],
  },
];

// M8.2 addition - kept internally consistent with the real
// backend/app/schemas/ai_gateway.py::GatewaySettingsRead shape this
// mirrors, even though this class is no longer instantiated by default
// (see GatewayDataProviderContext.tsx).
const GATEWAY_SETTINGS: GatewaySettings = {
  aiMode: "hybrid_recommended",
  requirePremiumApproval: true,
  maxAttemptsPerProvider: 2,
  defaultTimeoutSeconds: 60,
  capabilityProviderPreference: { default: ["local_ollama", "groq", "gemini_ai_studio", "claude"] },
  localModelRoles: { research: "qwen3:8b", writing: "llama3.1:8b" },
  capabilityLocalModelRole: {
    research_analysis: ["research"],
    outreach_email_generation: ["writing", "research"],
  },
};

// M8.3 Step 2 (Provider Management) addition - kept internally consistent
// with PROVIDERS above (a provider that's "connected" already has an
// implied credential; "not_configured" has none) even though this class
// is no longer instantiated by default - same disclosed-fixture
// discipline GATEWAY_SETTINGS already established. A mutable module-level
// map (not a fresh object per call) so saveProviderConfig()'s in-memory
// mutation is visible to a subsequent getProviderConfig() call, mirroring
// the real backend's own persisted-row behavior closely enough for
// offline dev.
const PROVIDER_CONFIGS = new Map<ProviderKey, ProviderConfig>(
  PROVIDERS.map((p) => [
    p.key,
    {
      providerKey: p.key,
      enabled: true,
      hasApiKey: p.status === "connected",
      baseUrl: p.key === "local_ollama" ? "http://localhost:11434/v1" : null,
      defaultModel: p.defaultModel,
      extraSettings: {},
      updatedAt: null,
      updatedByUserEmail: null,
    },
  ])
);

const PROVIDER_CONFIG_AUDIT = new Map<ProviderKey, ProviderConfigAuditEntry[]>();

export class MockGatewayProvider implements GatewayDataProvider {
  getOverview(): Promise<GatewayOverview> {
    return delay(OVERVIEW);
  }

  listProviders(): Promise<ProviderSummary[]> {
    return delay(PROVIDERS);
  }

  getProvider(key: ProviderKey): Promise<ProviderSummary | null> {
    return delay(PROVIDERS.find((p) => p.key === key) ?? null);
  }

  listActivity(): Promise<ActivityLogEntry[]> {
    return delay(ACTIVITY);
  }

  listApprovals(): Promise<ApprovalRequest[]> {
    return delay(APPROVALS);
  }

  listRoutingDecisions(): Promise<RoutingDecision[]> {
    return delay(ROUTING_DECISIONS);
  }

  getSettings(): Promise<GatewaySettings> {
    return delay(GATEWAY_SETTINGS);
  }

  getProviderConfig(key: ProviderKey): Promise<ProviderConfig | null> {
    return delay(PROVIDER_CONFIGS.get(key) ?? null);
  }

  saveProviderConfig(key: ProviderKey, patch: ProviderConfigWrite): Promise<ProviderConfig> {
    const current = PROVIDER_CONFIGS.get(key) ?? {
      providerKey: key,
      enabled: true,
      hasApiKey: false,
      baseUrl: null,
      defaultModel: null,
      extraSettings: {},
      updatedAt: null,
      updatedByUserEmail: null,
    };
    const fieldChanges: ProviderConfigAuditEntry["fieldChanges"] = {};
    const updated: ProviderConfig = { ...current };

    if (patch.enabled !== undefined && patch.enabled !== current.enabled) {
      fieldChanges.enabled = { old: current.enabled, new: patch.enabled };
      updated.enabled = patch.enabled;
    }
    if (patch.clearApiKey) {
      if (current.hasApiKey) fieldChanges.api_key = { old: "set", new: "unset" };
      updated.hasApiKey = false;
    } else if (patch.apiKey) {
      fieldChanges.api_key = { old: current.hasApiKey ? "set" : "unset", new: "set" };
      updated.hasApiKey = true;
    }
    if (patch.clearBaseUrl) {
      if (current.baseUrl !== null) fieldChanges.base_url = { old: current.baseUrl, new: null };
      updated.baseUrl = null;
    } else if (patch.baseUrl !== undefined && patch.baseUrl !== current.baseUrl) {
      fieldChanges.base_url = { old: current.baseUrl, new: patch.baseUrl };
      updated.baseUrl = patch.baseUrl;
    }
    if (patch.clearDefaultModel) {
      if (current.defaultModel !== null) fieldChanges.default_model = { old: current.defaultModel, new: null };
      updated.defaultModel = null;
    } else if (patch.defaultModel !== undefined && patch.defaultModel !== current.defaultModel) {
      fieldChanges.default_model = { old: current.defaultModel, new: patch.defaultModel };
      updated.defaultModel = patch.defaultModel;
    }
    if (patch.extraSettings !== undefined) {
      fieldChanges.extra_settings = { old: current.extraSettings, new: patch.extraSettings };
      updated.extraSettings = patch.extraSettings;
    }

    updated.updatedAt = new Date().toISOString();
    updated.updatedByUserEmail = "you@example.com";
    PROVIDER_CONFIGS.set(key, updated);

    if (Object.keys(fieldChanges).length > 0) {
      const entry: ProviderConfigAuditEntry = {
        id: `audit-${key}-${Date.now()}`,
        providerKey: key,
        changedAt: updated.updatedAt,
        changedByUserEmail: updated.updatedByUserEmail,
        fieldChanges,
      };
      PROVIDER_CONFIG_AUDIT.set(key, [entry, ...(PROVIDER_CONFIG_AUDIT.get(key) ?? [])]);
    }

    return delay(updated);
  }

  listProviderConfigAudit(key: ProviderKey, limit = 20): Promise<ProviderConfigAuditEntry[]> {
    return delay((PROVIDER_CONFIG_AUDIT.get(key) ?? []).slice(0, limit));
  }

  testConnection(key: ProviderKey): Promise<ConnectionTestResult> {
    const config = PROVIDER_CONFIGS.get(key);
    const provider = PROVIDERS.find((p) => p.key === key);
    if (!config || !provider) {
      return delay({ providerKey: key, success: false, message: `Unknown provider "${key}".`, latencyMs: null, availableModels: null });
    }
    if (!config.enabled) {
      return delay({ providerKey: key, success: false, message: `${provider.label} is disabled.`, latencyMs: null, availableModels: null });
    }
    const requiresKey = provider.tier !== "local";
    if (requiresKey && !config.hasApiKey) {
      return delay({
        providerKey: key,
        success: false,
        message: `${provider.label} has no API key configured.`,
        latencyMs: null,
        availableModels: null,
      });
    }
    return delay({
      providerKey: key,
      success: true,
      message: "Connected",
      latencyMs: provider.avgLatencyMs ?? 250,
      availableModels: provider.defaultModel ? [provider.defaultModel] : [],
    });
  }
}
