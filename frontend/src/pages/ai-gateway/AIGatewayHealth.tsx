import { Card, PlaceholderNotice, StatusIndicator } from "../../design-system";
import type { StatusKind } from "../../design-system";
import { useProviders } from "../../ai-gateway/hooks/useProviders";
import { useProviderCapabilities } from "../../ai-gateway/hooks/useProviderCapabilities";
import { ProviderCapabilityViewer } from "../../ai-gateway/components/ProviderCapabilityViewer";
import { GatewayDiagnosticsPanel } from "../../ai-gateway/components/GatewayDiagnosticsPanel";
import { getProviderIdentity } from "../../ai-gateway/identity/providerIdentity";
import type { ProviderSummary } from "../../ai-gateway/types";

const STATUS_DISPLAY: Record<ProviderSummary["status"], { kind: StatusKind; label: string }> = {
  connected: { kind: "success", label: "Healthy" },
  not_configured: { kind: "idle", label: "Not configured" },
  degraded: { kind: "waiting", label: "Degraded" },
  down: { kind: "failed", label: "Down" },
};

/**
 * AIGatewayHealth — /ai-gateway/health. Admin/diagnostics page.
 * Per-provider connection status, the real Provider Capability Viewer
 * (M8.3 Step 5, sourced from `GET /ai-gateway/capabilities` - replaced the
 * earlier mock-only `CapabilityMatrix` placeholder), and (M8.3 Step 6) the
 * real Gateway Diagnostics panel (`GatewayDiagnosticsPanel`, sourced from
 * `GET /ai-gateway/diagnostics`) - built entirely from existing telemetry
 * (provider health, live routing outcomes, recent request failures), never
 * a second routing/capability engine. Failover events and routing
 * statistics (as distinct, historical CHARTS - not the same thing as the
 * diagnostic findings Step 6 now surfaces) remain out of scope for this
 * milestone, per Section 11's own remaining build order.
 */
export default function AIGatewayHealth() {
  const { data: providers, isLoading, error } = useProviders();
  const { data: capabilities, isLoading: capabilitiesLoading, error: capabilitiesError } = useProviderCapabilities();

  if (error) return <PlaceholderNotice kind="no-data" reason={error} />;

  return (
    <div className="flex flex-col gap-6">
      <Card className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-slate-100">Provider Health</h2>
        {isLoading ? (
          <p className="text-xs text-slate-500">Loading…</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {providers.map((provider) => (
              <li key={provider.key} className="flex items-center justify-between text-xs">
                <span className="text-slate-300">{getProviderIdentity(provider.key).label}</span>
                <StatusIndicator kind={STATUS_DISPLAY[provider.status].kind} label={STATUS_DISPLAY[provider.status].label} />
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-slate-100">Provider Capabilities</h2>
        {capabilitiesError ? (
          <PlaceholderNotice kind="no-data" reason={capabilitiesError} />
        ) : capabilitiesLoading ? (
          <p className="text-xs text-slate-500">Loading…</p>
        ) : (
          <ProviderCapabilityViewer providers={capabilities} />
        )}
      </Card>

      <GatewayDiagnosticsPanel />

      <PlaceholderNotice
        kind="not-implemented"
        reason="Failover event history and routing statistics charts — not yet implemented in this foundation milestone."
      />
    </div>
  );
}
