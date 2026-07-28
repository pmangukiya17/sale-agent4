import { useState } from "react";
import { Badge, Button, Card, PlaceholderNotice, Select, StatusIndicator } from "../../design-system";
import type { BadgeTone } from "../../design-system";
import { useRoutingSimulator } from "../hooks/useRoutingSimulator";
import type { ProviderKey, RoutingSimulationNode, RoutingSimulationNodeState } from "../types";

const CAPABILITY_OPTIONS: { value: string; label: string }[] = [
  { value: "research_analysis", label: "Prospect Research" },
  { value: "outreach_email_generation", label: "Email Drafting" },
  { value: "default", label: "General (default preference)" },
];

const AI_MODE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Use live setting" },
  { value: "local_only", label: "Local only" },
  { value: "hybrid_recommended", label: "Hybrid (recommended)" },
  { value: "automatic_premium", label: "Automatic premium" },
  { value: "premium_only", label: "Premium only" },
];

const PROVIDER_OVERRIDE_KEYS: ProviderKey[] = ["local_ollama", "groq", "gemini_ai_studio", "gemini", "claude", "openai"];
const PROVIDER_LABELS: Record<ProviderKey, string> = {
  local_ollama: "Ollama",
  groq: "Groq",
  gemini_ai_studio: "Gemini AI Studio",
  gemini: "Gemini",
  claude: "Claude",
  openai: "OpenAI",
};

const STATE_TONE: Record<RoutingSimulationNodeState, BadgeTone> = {
  would_call: "success",
  requires_approval: "warning",
  skipped_not_configured: "neutral",
  skipped_capability_mismatch: "danger",
  skipped_not_reached: "neutral",
};

const STATE_LABEL: Record<RoutingSimulationNodeState, string> = {
  would_call: "Would call",
  requires_approval: "Requires approval",
  skipped_not_configured: "Not configured",
  skipped_capability_mismatch: "Capability mismatch",
  skipped_not_reached: "Not reached",
};

const ROLE_LABEL: Record<RoutingSimulationNode["role"], string> = {
  primary: "Primary",
  fallback: "Fallback",
  premium: "Premium",
};

function formatCost(value: number | null): string {
  if (value === null) return "—";
  return value < 0.01 ? `$${value.toFixed(6)}` : `$${value.toFixed(4)}`;
}

/**
 * RoutingSimulatorPanel — M8.3 Step 4 (AI Gateway Management & Control,
 * Routing Simulator). READ-ONLY: this panel only ever calls
 * `useRoutingSimulator().run()` (POST /ai-gateway/routing/simulate),
 * which never mutates any setting and never attempts a real provider
 * call - `aiModeOverride`/`providerOverrides` are purely hypothetical
 * "what would happen if..." inputs to a pure backend computation, never
 * persisted anywhere. No Save button exists on this panel by design.
 *
 * Shows the COMPLETE candidate chain (local + free + premium, in
 * preference order) for the selected capability - every candidate gets a
 * node with its own state/reason, including ones that would never
 * actually be reached, per the CEO's own Step 4 requirements. The
 * "Capability filters" section surfaces `requestedCapabilities`/
 * `capabilityExcluded` so an admin can see WHY a candidate was skipped
 * for lacking structured output / tool calling / deep reasoning support,
 * distinct from simply being unconfigured.
 */
export function RoutingSimulatorPanel() {
  const { result, isSimulating, error, run } = useRoutingSimulator();

  const [capability, setCapability] = useState(CAPABILITY_OPTIONS[0].value);
  const [aiModeOverride, setAiModeOverride] = useState("");
  const [providerOverrides, setProviderOverrides] = useState<Record<ProviderKey, "real" | "enabled" | "disabled">>({
    local_ollama: "real",
    groq: "real",
    gemini_ai_studio: "real",
    gemini: "real",
    claude: "real",
    openai: "real",
  });

  function setOverride(key: ProviderKey, value: "real" | "enabled" | "disabled") {
    setProviderOverrides((prev) => ({ ...prev, [key]: value }));
  }

  async function handleRun() {
    const overrides: Record<string, boolean> = {};
    for (const key of PROVIDER_OVERRIDE_KEYS) {
      const choice = providerOverrides[key];
      if (choice === "enabled") overrides[key] = true;
      if (choice === "disabled") overrides[key] = false;
    }
    await run({
      capability,
      aiModeOverride: aiModeOverride || undefined,
      providerEnabledOverrides: Object.keys(overrides).length > 0 ? overrides : undefined,
    });
  }

  return (
    <Card className="flex flex-col gap-5">
      <div>
        <h2 className="text-sm font-semibold text-slate-100">Routing Simulator</h2>
        <p className="mt-0.5 text-[11px] text-slate-500">
          Explains what would happen for a capability under real or hypothetical settings - read-only, never executes
          a real call or changes any setting.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div>
          <label className="text-[10px] uppercase tracking-wide text-slate-500">Capability</label>
          <Select value={capability} onChange={(e) => setCapability(e.target.value)} className="mt-1">
            {CAPABILITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-wide text-slate-500">AI mode (hypothetical)</label>
          <Select value={aiModeOverride} onChange={(e) => setAiModeOverride(e.target.value)} className="mt-1">
            {AI_MODE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex items-end">
          <Button size="sm" onClick={handleRun} isLoading={isSimulating} className="w-full">
            Run simulation
          </Button>
        </div>
      </div>

      <div className="border-t border-border-hairline pt-4">
        <p className="mb-2 text-[10px] uppercase tracking-wide text-slate-500">
          Provider overrides (hypothetical - never changes real configuration)
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {PROVIDER_OVERRIDE_KEYS.map((key) => (
            <div key={key} className="flex items-center justify-between gap-2 rounded-lg border border-border-hairline bg-surface-2 px-2.5 py-1.5">
              <span className="text-xs text-slate-300">{PROVIDER_LABELS[key]}</span>
              <Select
                value={providerOverrides[key]}
                onChange={(e) => setOverride(key, e.target.value as "real" | "enabled" | "disabled")}
                className="h-7 w-28 text-[11px]"
              >
                <option value="real">Real state</option>
                <option value="enabled">Force enabled</option>
                <option value="disabled">Force disabled</option>
              </Select>
            </div>
          ))}
        </div>
      </div>

      {error && <PlaceholderNotice kind="no-data" reason={error} />}

      {result && (
        <div className="flex flex-col gap-4 border-t border-border-hairline pt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-medium text-slate-200">
                {result.featureLabel} · AI mode used: <span className="text-slate-400">{result.aiModeUsed}</span>
              </h3>
              <p className="mt-0.5 text-[11px] text-slate-500">{result.outcomeDetail}</p>
            </div>
            <StatusIndicator
              kind={result.outcome === "success" ? "success" : result.outcome === "waiting" ? "waiting" : "failed"}
              label={result.outcome === "success" ? "Would succeed" : result.outcome === "waiting" ? "Would wait for approval" : "Would fail"}
            />
          </div>

          <div>
            <p className="mb-1.5 text-[10px] uppercase tracking-wide text-slate-500">Capability filters</p>
            {result.requestedCapabilities.length === 0 ? (
              <p className="text-xs text-slate-500">This request has no special capability requirements.</p>
            ) : (
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                <span>Requires:</span>
                {result.requestedCapabilities.map((cap) => (
                  <Badge key={cap} tone="info">
                    {cap.replace("_", " ")}
                  </Badge>
                ))}
                {result.capabilityExcluded.length > 0 && (
                  <span className="ml-2">
                    Excluded for this reason: <span className="text-slate-300">{result.capabilityExcluded.join(", ")}</span>
                  </span>
                )}
              </div>
            )}
          </div>

          <div>
            <p className="mb-1.5 text-[10px] uppercase tracking-wide text-slate-500">Decision chain (in order)</p>
            <ul className="flex flex-col gap-2">
              {result.nodes.map((node) => (
                <li key={`${node.role}-${node.providerKey}`} className="rounded-lg border border-border-hairline bg-surface-2 p-3 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
                        #{node.position + 1} · {ROLE_LABEL[node.role]}
                      </span>
                      <span className="font-medium text-slate-200">{node.label}</span>
                      <Badge tone={node.tier === "premium" ? "warning" : node.tier === "free" ? "success" : "info"}>{node.tier}</Badge>
                      {node.overridden && <Badge tone="ai">simulated</Badge>}
                    </div>
                    <Badge tone={STATE_TONE[node.state]}>{STATE_LABEL[node.state]}</Badge>
                  </div>
                  <p className="mt-1.5 text-slate-400">{node.reason}</p>
                  <div className="mt-1.5 flex flex-wrap gap-3 text-[11px] text-slate-500">
                    <span>Cost / 1k in: {formatCost(node.costPer1kInputUsd)}</span>
                    <span>Cost / 1k out: {formatCost(node.costPer1kOutputUsd)}</span>
                    {node.estimatedCostUsd !== null && <span>Est. cost this call: {formatCost(node.estimatedCostUsd)}</span>}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Card>
  );
}
