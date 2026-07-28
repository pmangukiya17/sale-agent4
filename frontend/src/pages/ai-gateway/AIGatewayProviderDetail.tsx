import { Link, useParams } from "react-router-dom";
import { Card, PlaceholderNotice, StatusIndicator } from "../../design-system";
import type { StatusKind } from "../../design-system";
import { useProvider } from "../../ai-gateway/hooks/useProviders";
import { TierBadge } from "../../ai-gateway/components/TierBadge";
import { CostPill } from "../../ai-gateway/components/CostPill";
import { ProviderConfigPanel } from "../../ai-gateway/components/ProviderConfigPanel";
import { getProviderIdentity, PROVIDER_IDENTITIES } from "../../ai-gateway/identity/providerIdentity";
import type { ProviderKey, ProviderSummary } from "../../ai-gateway/types";

const STATUS_DISPLAY: Record<ProviderSummary["status"], { kind: StatusKind; label: string }> = {
  connected: { kind: "success", label: "Connected" },
  not_configured: { kind: "idle", label: "Not configured" },
  degraded: { kind: "waiting", label: "Degraded" },
  down: { kind: "failed", label: "Down" },
};

const CAPABILITY_LABELS: Record<string, string> = {
  structured_output: "Structured output",
  tool_calling: "Tool calling",
  streaming: "Streaming",
  vision: "Vision",
  reasoning_support: "Reasoning",
};

/**
 * AIGatewayProviderDetail — /ai-gateway/providers/:providerKey. A summary
 * card (status, tier, default model, capabilities, cost, latency - all
 * M8.2, read-only) plus, as of M8.3 Step 2, a real Provider Configuration
 * panel (ProviderConfigPanel - enable/disable, API key, base URL, default
 * model, Test Connection, and admin-only configuration history). Usage
 * history and a live failure log remain out of scope (see
 * PlaceholderNotice below) - those depend on capabilities this milestone
 * still doesn't have (persisted per-attempt chain history, live failure
 * streaming).
 */
export default function AIGatewayProviderDetail() {
  const { providerKey } = useParams<{ providerKey: string }>();
  const isKnownKey = Boolean(providerKey && providerKey in PROVIDER_IDENTITIES);
  const { data: provider, isLoading, error } = useProvider(isKnownKey ? (providerKey as ProviderKey) : undefined);

  if (!isKnownKey) {
    return <PlaceholderNotice kind="no-data" reason={`Unknown provider "${providerKey}".`} />;
  }

  const identity = getProviderIdentity(providerKey as ProviderKey);

  return (
    <div className="flex flex-col gap-6">
      <Link to="/ai-gateway/providers" className="text-xs font-medium text-slate-500 hover:text-slate-300">
        ← AI Providers
      </Link>

      {isLoading || !provider ? (
        error ? (
          <PlaceholderNotice kind="no-data" reason={error} />
        ) : (
          <div className="h-48 animate-pulse rounded-card border border-border-hairline bg-surface-1" />
        )
      ) : (
        <>
          <Card accent={identity.accent} className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-slate-100">{identity.label}</h2>
                <TierBadge tier={provider.tier} />
              </div>
              <StatusIndicator kind={STATUS_DISPLAY[provider.status].kind} label={STATUS_DISPLAY[provider.status].label} />
            </div>

            <dl className="grid grid-cols-2 gap-4 text-xs text-slate-500 sm:grid-cols-4">
              <div>
                <dt className="text-[10px] uppercase tracking-wide">Default model</dt>
                <dd className="mt-0.5 text-slate-200">{provider.defaultModel ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-[10px] uppercase tracking-wide">Cost / 1K input</dt>
                <dd className="mt-0.5">
                  <CostPill usd={provider.costPer1kInputUsd} />
                </dd>
              </div>
              <div>
                <dt className="text-[10px] uppercase tracking-wide">Cost / 1K output</dt>
                <dd className="mt-0.5">
                  <CostPill usd={provider.costPer1kOutputUsd} />
                </dd>
              </div>
              <div>
                <dt className="text-[10px] uppercase tracking-wide">Avg latency</dt>
                <dd className="mt-0.5 tabular-nums text-slate-200">
                  {provider.avgLatencyMs ? `${provider.avgLatencyMs}ms` : "—"}
                </dd>
              </div>
            </dl>

            <div>
              <p className="text-[10px] uppercase tracking-wide text-slate-500">Capabilities</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {provider.capabilities.map((capability) => (
                  <span
                    key={capability}
                    className="rounded-pill border border-border-hairline bg-surface-2 px-2 py-0.5 text-[11px] text-slate-300"
                  >
                    {CAPABILITY_LABELS[capability] ?? capability}
                  </span>
                ))}
              </div>
            </div>
          </Card>

          <ProviderConfigPanel providerKey={providerKey as ProviderKey} />

          <PlaceholderNotice
            kind="not-implemented"
            reason="Usage history and a live failure log are not yet implemented in this milestone."
          />
        </>
      )}
    </div>
  );
}
