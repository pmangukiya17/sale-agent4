import type {
  ActivityLogEntry,
  ApprovalRequest,
  ConnectionTestResult,
  GatewayOverview,
  GatewaySettings,
  ModelRole,
  ModelRoleWrite,
  DiagnosticFinding,
  GatewayDiagnostics,
  PremiumPreauthorization,
  ProviderCapability,
  ProviderConfig,
  ProviderConfigAuditEntry,
  ProviderConfigWrite,
  ProviderKey,
  ProviderSummary,
  RoutingDecision,
  RoutingSimulationNode,
  RoutingSimulationRequestInput,
  RoutingSimulationResult,
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

// M8.3 Step 7 (Premium Approval UI) addition - `status` is now a real,
// mutable field (approveRequest()/rejectRequest() below flip it in place,
// same "mutable module-level fixture" discipline PROVIDER_CONFIGS/
// MODEL_ROLES above already establish) rather than every row being
// implicitly "still pending" the way it was before this step.
const APPROVALS: ApprovalRequest[] = [
  {
    id: "appr-1",
    status: "pending",
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
    status: "pending",
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

// M8.3 Step 7 addition - a mutable, in-memory audit trail
// approveRequest()/rejectRequest() append to, mirroring the real backend's
// append-only AIPremiumPreauthorization table closely enough for offline
// dev (see that model's own "never mutated once written" docstring) -
// most-recent-first, same ordering listApprovalHistory() below returns.
const APPROVAL_HISTORY: PremiumPreauthorization[] = [];
const PREAUTH_WINDOW_MINUTES = 120;

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

// M8.3 Step 3 (Model Role Management) addition - kept internally
// consistent with GATEWAY_SETTINGS.localModelRoles above (same two
// starting roles, same fixture models) even though this class is no
// longer instantiated by default. A mutable module-level map so
// saveModelRole()/deleteModelRole()'s in-memory mutation is visible to a
// subsequent listModelRoles() call, mirroring the real backend's own
// persisted-row behavior closely enough for offline dev.
const MODEL_ROLES = new Map<string, ModelRole>([
  ["research", { roleName: "research", model: "qwen3:8b", enabled: true, updatedAt: null, updatedByUserEmail: null }],
  ["writing", { roleName: "writing", model: "llama3.1:8b", enabled: true, updatedAt: null, updatedByUserEmail: null }],
]);

// M8.3 Step 5 (Provider Capability Viewer) addition - a fresh, deliberately
// honest fixture rather than reusing PROVIDERS[].capabilities (that flat
// string list predates this milestone and was never meant to distinguish
// provider-level facts from per-model overrides - see CapabilityMatrix.tsx's
// own docstring). `streaming` is false for every provider here, matching
// the real backend's own disclosed limitation (AIGateway.stream() itself
// raises NotImplementedError unconditionally - see
// app/ai_gateway/capabilities.py's module docstring) rather than the SDK's
// real streaming support. `providerLevel` and `effective` are identical for
// every provider - `hasModelOverride: false` everywhere - because the real
// backend's `_CAPABILITY_OVERRIDES` table has zero registered entries
// today; this fixture stays honest about that rather than inventing a
// demo override, exactly like the real endpoint does.
const PROVIDER_CAPABILITIES: Record<ProviderKey, ProviderCapability> = {
  local_ollama: {
    providerKey: "local_ollama",
    label: "Ollama",
    tier: "local",
    defaultModel: "llama3.1:8b",
    providerLevel: {
      structuredOutput: true,
      toolCalling: true,
      streaming: false,
      vision: false,
      embeddings: false,
      reasoningSupport: false,
      maxContextTokens: 128000,
      maxOutputTokens: 4096,
    },
    effective: {
      structuredOutput: true,
      toolCalling: true,
      streaming: false,
      vision: false,
      embeddings: false,
      reasoningSupport: false,
      maxContextTokens: 128000,
      maxOutputTokens: 4096,
    },
    hasModelOverride: false,
    overriddenFields: [],
  },
  groq: {
    providerKey: "groq",
    label: "Groq",
    tier: "free",
    defaultModel: "llama-3.3-70b-versatile",
    providerLevel: {
      structuredOutput: true,
      toolCalling: true,
      streaming: false,
      vision: false,
      embeddings: false,
      reasoningSupport: false,
      maxContextTokens: 131072,
      maxOutputTokens: 8192,
    },
    effective: {
      structuredOutput: true,
      toolCalling: true,
      streaming: false,
      vision: false,
      embeddings: false,
      reasoningSupport: false,
      maxContextTokens: 131072,
      maxOutputTokens: 8192,
    },
    hasModelOverride: false,
    overriddenFields: [],
  },
  gemini_ai_studio: {
    providerKey: "gemini_ai_studio",
    label: "Gemini AI Studio",
    tier: "free",
    defaultModel: null,
    providerLevel: {
      structuredOutput: true,
      toolCalling: false,
      streaming: false,
      vision: true,
      embeddings: false,
      reasoningSupport: false,
      maxContextTokens: null,
      maxOutputTokens: null,
    },
    effective: {
      structuredOutput: true,
      toolCalling: false,
      streaming: false,
      vision: true,
      embeddings: false,
      reasoningSupport: false,
      maxContextTokens: null,
      maxOutputTokens: null,
    },
    hasModelOverride: false,
    overriddenFields: [],
  },
  gemini: {
    providerKey: "gemini",
    label: "Gemini",
    tier: "premium",
    defaultModel: "gemini-3.6-flash",
    providerLevel: {
      structuredOutput: true,
      toolCalling: true,
      streaming: false,
      vision: true,
      embeddings: true,
      reasoningSupport: true,
      maxContextTokens: 1000000,
      maxOutputTokens: 8192,
    },
    effective: {
      structuredOutput: true,
      toolCalling: true,
      streaming: false,
      vision: true,
      embeddings: true,
      reasoningSupport: true,
      maxContextTokens: 1000000,
      maxOutputTokens: 8192,
    },
    hasModelOverride: false,
    overriddenFields: [],
  },
  claude: {
    providerKey: "claude",
    label: "Claude",
    tier: "premium",
    defaultModel: "claude-sonnet-4-5",
    providerLevel: {
      structuredOutput: true,
      toolCalling: true,
      streaming: false,
      vision: false,
      embeddings: false,
      reasoningSupport: true,
      maxContextTokens: 200000,
      maxOutputTokens: 8192,
    },
    effective: {
      structuredOutput: true,
      toolCalling: true,
      streaming: false,
      vision: false,
      embeddings: false,
      reasoningSupport: true,
      maxContextTokens: 200000,
      maxOutputTokens: 8192,
    },
    hasModelOverride: false,
    overriddenFields: [],
  },
  openai: {
    providerKey: "openai",
    label: "OpenAI",
    tier: "premium",
    defaultModel: null,
    providerLevel: {
      structuredOutput: true,
      toolCalling: true,
      streaming: false,
      vision: true,
      embeddings: true,
      reasoningSupport: false,
      maxContextTokens: null,
      maxOutputTokens: null,
    },
    effective: {
      structuredOutput: true,
      toolCalling: true,
      streaming: false,
      vision: true,
      embeddings: true,
      reasoningSupport: false,
      maxContextTokens: null,
      maxOutputTokens: null,
    },
    hasModelOverride: false,
    overriddenFields: [],
  },
};

// M8.3 Step 6 (Gateway Diagnostics) addition - kept internally consistent
// with PROVIDERS/PROVIDER_CONFIGS above (gemini_ai_studio and openai are
// the two "not_configured" providers there, so they're the two
// "enabled but not configured" findings here too) and with GATEWAY_SETTINGS
// (requirePremiumApproval: true, aiMode: hybrid_recommended) and
// ROUTING_DECISIONS (route-2/outreach_email_generation is "waiting" there,
// so it's the one routing finding here) - same "one coherent story across
// every mock method" discipline this file's own docstring already
// establishes, even though this class is no longer instantiated by
// default. generated_at is computed fresh per call (delay()'d), matching
// the real backend's own "no caching, always a fresh snapshot" behavior.
const DIAGNOSTIC_FINDINGS: DiagnosticFinding[] = [
  {
    category: "provider_health",
    severity: "warning",
    title: "Gemini AI Studio is enabled but not configured",
    detail:
      "Gemini AI Studio is enabled but has no valid credentials/base URL - the router will silently skip it at request time and fall through to the next candidate.",
    recommendation: "Add credentials for Gemini AI Studio in Provider Management, or disable it there to make the gap explicit rather than silent.",
    providerKey: "gemini_ai_studio",
    capability: null,
  },
  {
    category: "provider_health",
    severity: "warning",
    title: "OpenAI is enabled but not configured",
    detail:
      "OpenAI is enabled but has no valid credentials/base URL - the router will silently skip it at request time and fall through to the next candidate.",
    recommendation: "Add credentials for OpenAI in Provider Management, or disable it there to make the gap explicit rather than silent.",
    providerKey: "openai",
    capability: null,
  },
  {
    category: "routing",
    severity: "info",
    title: "'Email Drafting' will require premium approval",
    detail:
      "Local/free tier candidates are currently exhausted for 'Email Drafting'; the next request will pause for an explicit premium approval rather than complete automatically.",
    recommendation: "This is expected behavior under the current settings - no action needed unless the approval step itself is undesired.",
    providerKey: null,
    capability: "outreach_email_generation",
  },
  {
    category: "routing",
    severity: "warning",
    title: "Groq failed 2 times in the last 24 hours",
    detail: "Recent AI Gateway requests to Groq failed with 'ProviderTimeoutError'.",
    recommendation: "Check Groq's credentials/connectivity in Provider Management, or review recent Activity for this provider.",
    providerKey: "groq",
    capability: null,
  },
];

function buildDiagnostics(): GatewayDiagnostics {
  return {
    generatedAt: new Date().toISOString(),
    findings: DIAGNOSTIC_FINDINGS,
    errorCount: DIAGNOSTIC_FINDINGS.filter((f) => f.severity === "error").length,
    warningCount: DIAGNOSTIC_FINDINGS.filter((f) => f.severity === "warning").length,
    infoCount: DIAGNOSTIC_FINDINGS.filter((f) => f.severity === "info").length,
  };
}

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

  listModelRoles(): Promise<ModelRole[]> {
    return delay([...MODEL_ROLES.values()].sort((a, b) => a.roleName.localeCompare(b.roleName)));
  }

  saveModelRole(roleName: string, patch: ModelRoleWrite): Promise<ModelRole> {
    const current = MODEL_ROLES.get(roleName);
    if (!current && !patch.model) {
      return Promise.reject(new Error(`Cannot create model role "${roleName}" without a model value.`));
    }
    const updated: ModelRole = {
      roleName,
      model: patch.model ?? current?.model ?? "",
      enabled: patch.enabled ?? current?.enabled ?? true,
      updatedAt: new Date().toISOString(),
      updatedByUserEmail: "you@example.com",
    };
    MODEL_ROLES.set(roleName, updated);
    return delay(updated);
  }

  deleteModelRole(roleName: string): Promise<void> {
    MODEL_ROLES.delete(roleName);
    return delay(undefined);
  }

  simulateRouting(request: RoutingSimulationRequestInput): Promise<RoutingSimulationResult> {
    // M8.3 Step 4 (Routing Simulator) fixture - a simplified, client-side
    // approximation of the real backend's build_simulation() logic, kept
    // internally consistent with PROVIDERS above (same default preference
    // order: local_ollama -> groq -> gemini_ai_studio -> claude(premium)).
    // Good enough for offline dev; the real decision logic lives entirely
    // server-side (app.ai_gateway.routing_simulator.build_simulation()).
    const aiMode = request.aiModeOverride ?? GATEWAY_SETTINGS.aiMode;
    const overrides = request.providerEnabledOverrides ?? {};
    const preferenceOrder: ProviderKey[] = ["local_ollama", "groq", "gemini_ai_studio", "claude"];

    const effectiveConfigured = (key: ProviderKey): boolean => {
      const config = PROVIDER_CONFIGS.get(key);
      if (key in overrides) return overrides[key];
      return Boolean(config?.enabled && (PROVIDERS.find((p) => p.key === key)?.status === "connected"));
    };

    let chainKeys: ProviderKey[];
    let premiumKeys: ProviderKey[];
    if (aiMode === "local_only") {
      chainKeys = preferenceOrder.filter((k) => PROVIDERS.find((p) => p.key === k)?.tier === "local");
      premiumKeys = [];
    } else if (aiMode === "premium_only") {
      chainKeys = [];
      premiumKeys = preferenceOrder.filter((k) => PROVIDERS.find((p) => p.key === k)?.tier === "premium");
    } else if (aiMode === "automatic_premium") {
      chainKeys = preferenceOrder;
      premiumKeys = [];
    } else {
      chainKeys = preferenceOrder.filter((k) => PROVIDERS.find((p) => p.key === k)?.tier !== "premium");
      premiumKeys = preferenceOrder.filter((k) => PROVIDERS.find((p) => p.key === k)?.tier === "premium");
    }

    const nodes: RoutingSimulationNode[] = [];
    let reached = false;
    let outcome: RoutingSimulationResult["outcome"] = "failed";
    let outcomeDetail = "No configured provider is available for this capability.";

    const pushNode = (key: ProviderKey, role: RoutingSimulationNode["role"], position: number) => {
      const provider = PROVIDERS.find((p) => p.key === key);
      const label = provider?.label ?? key;
      const tier = provider?.tier ?? "premium";
      const overridden = key in overrides;
      const base = {
        providerKey: key,
        label,
        tier,
        role,
        position,
        configured: Boolean(PROVIDER_CONFIGS.get(key)?.enabled && provider?.status === "connected"),
        overridden,
        costPer1kInputUsd: provider?.costPer1kInputUsd ?? null,
        costPer1kOutputUsd: provider?.costPer1kOutputUsd ?? null,
      };

      if (reached) {
        nodes.push({ ...base, state: "skipped_not_reached", reason: `An earlier provider already satisfied this request; ${label} would not be reached.`, estimatedCostUsd: null });
        return;
      }
      if (!effectiveConfigured(key)) {
        nodes.push({ ...base, state: "skipped_not_configured", reason: `${label} is not configured${overridden ? " (simulated override)" : ""}.`, estimatedCostUsd: null });
        return;
      }
      const estimatedCostUsd = provider ? (provider.costPer1kInputUsd ?? 0) * 4 : null;
      if (role === "premium" && GATEWAY_SETTINGS.requirePremiumApproval) {
        reached = true;
        outcome = "waiting";
        outcomeDetail = `${label} would require your explicit premium approval before use.`;
        nodes.push({ ...base, state: "requires_approval", reason: `Local/free tier exhausted for this capability${overridden ? " (simulated override)" : ""}. ${label} would require your explicit approval before use.`, estimatedCostUsd });
      } else {
        reached = true;
        outcome = "success";
        outcomeDetail = `${label} is configured${overridden ? " (simulated override)" : ""} and would serve this request.`;
        nodes.push({ ...base, state: "would_call", reason: `${label} is configured${overridden ? " (simulated override)" : ""} and next in the chain - this is the provider that would actually be used.`, estimatedCostUsd });
      }
    };

    let position = 0;
    chainKeys.forEach((key, i) => pushNode(key, i === 0 ? "primary" : "fallback", position++));
    premiumKeys.forEach((key) => pushNode(key, "premium", position++));

    const featureLabel = request.capability === "research_analysis" ? "Prospect Research" : request.capability === "outreach_email_generation" ? "Email Drafting" : "General";

    return delay({
      capability: request.capability,
      featureLabel,
      aiModeUsed: aiMode,
      requestedCapabilities: request.capability === "research_analysis" || request.capability === "outreach_email_generation" ? ["structured_output"] : [],
      capabilityExcluded: [],
      nodes,
      outcome,
      outcomeDetail,
    });
  }

  listProviderCapabilities(): Promise<ProviderCapability[]> {
    return delay(PROVIDERS.map((p) => PROVIDER_CAPABILITIES[p.key]));
  }

  getDiagnostics(): Promise<GatewayDiagnostics> {
    return delay(buildDiagnostics());
  }

  approveRequest(approvalId: string): Promise<PremiumPreauthorization> {
    return delay(decidePremiumRequest(approvalId, "approved"));
  }

  rejectRequest(approvalId: string): Promise<PremiumPreauthorization> {
    return delay(decidePremiumRequest(approvalId, "rejected"));
  }

  listApprovalHistory(limit = 100): Promise<PremiumPreauthorization[]> {
    return delay(APPROVAL_HISTORY.slice(0, limit));
  }
}

// M8.3 Step 7 (Premium Approval UI) - shared by approveRequest()/
// rejectRequest() above, mirroring the real backend's own
// grant_preauthorization() (writes exactly one new AIPremiumPreauthorization
// row, never updates) plus its route layer's own 404-for-unknown-id guard.
// Every OTHER pending fixture row for the SAME feature/company also flips
// status here - the real backend's `status` is scoped to (company,
// capability), not the one literal row that happened to be Approved/
// Rejected, and this fixture stays honest about that rather than only
// updating the clicked card (see ApprovalRequestRead.status's own
// docstring in ../types.ts for the real semantics this approximates).
function decidePremiumRequest(approvalId: string, decision: PremiumPreauthorization["decision"]): PremiumPreauthorization {
  const source = APPROVALS.find((a) => a.id === approvalId);
  if (!source) {
    throw new Error(`Unknown approval request "${approvalId}".`);
  }

  const decidedAt = new Date().toISOString();
  const record: PremiumPreauthorization = {
    id: `preauth-${approvalId}-${Date.now()}`,
    companyName: source.companyName,
    capability: source.feature,
    feature: source.feature,
    decision,
    decidedBy: "you@example.com",
    decidedAt,
    expiresAt: decision === "approved" ? new Date(Date.now() + PREAUTH_WINDOW_MINUTES * 60_000).toISOString() : null,
    sourceReason: source.reason,
    sourceEstimatedCostUsd: source.estimatedCostUsd,
  };
  APPROVAL_HISTORY.unshift(record);

  for (const approval of APPROVALS) {
    if (approval.companyName === source.companyName && approval.feature === source.feature) {
      approval.status = decision;
    }
  }

  return record;
}
