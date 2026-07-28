import { Card, PlaceholderNotice, StatusIndicator } from "../../design-system";
import type { StatusKind } from "../../design-system";
import { useProviders } from "../../ai-gateway/hooks/useProviders";
import { CapabilityMatrix } from "../../ai-gateway/components/CapabilityMatrix";
import { getProviderIdentity } from "../../ai-gateway/identity/providerIdentity";
import type { ProviderSummary } from "../../ai-gateway/types";

const STATUS_DISPLAY: Record<ProviderSummary["status"], { kind: StatusKind; label: string }> = {
  connected: { kind: "success", label: "Healthy" },
  not_configured: { kind: "idle", label: "Not configured" },
  degraded: { kind: "waiting", label: "Degraded" },
  down: { kind: "failed", label: "Down" },
};

/**
 * AIGatewayHealth — /ai-gateway/health. Admin/diagnostics page. Two real
 * things this milestone can show from mock data (per-provider connection
 * status, and the `CapabilityMatrix` placeholder); failover events,
 * routing statistics, and diagnostics warnings all depend on live/backend
 * signals this milestone doesn't have, so they render as one
 * PlaceholderNotice rather than fabricated rows.
 */
export default function AIGatewayHealth() {
  const { data: providers, isLoading, error } = useProviders();

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
        <h2 className="text-sm font-semibold text-slate-100">Capability Matrix</h2>
        {isLoading ? <p className="text-xs text-slate-500">Loading…</p> : <CapabilityMatrix providers={providers} />}
      </Card>

      <PlaceholderNotice
        kind="not-implemented"
        reason="Failover events, routing statistics, and diagnostics warnings — not yet implemented in this foundation milestone."
      />
    </div>
  );
}
