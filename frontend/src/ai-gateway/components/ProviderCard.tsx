import { Link } from "react-router-dom";
import { Card, StatusIndicator } from "../../design-system";
import type { StatusKind } from "../../design-system";
import { getProviderIdentity } from "../identity/providerIdentity";
import { TierBadge } from "./TierBadge";
import { CostPill } from "./CostPill";
import type { ProviderSummary } from "../types";

/**
 * ProviderCard — one entry on the AI Providers grid (/ai-gateway/providers).
 * `Card accent={identity.accent}` gives each provider its own persistent
 * ambient identity (Section 7.1 of the approved architecture doc); `active`
 * is deliberately NOT wired to anything in this milestone (no live
 * updates), so every card sits at ambient glow only - honest, since
 * nothing here is "genuinely happening right now" without a real backend
 * signal behind it (Card's own documented rule).
 *
 * Unconfigured providers (`status === "not_configured"`) render visibly
 * quieter (muted stats row, "Set up" instead of "Details" CTA) rather than
 * being hidden - the fixed six-provider set is a known fact, not something
 * to hide part of.
 */
const STATUS_DISPLAY: Record<ProviderSummary["status"], { kind: StatusKind; label: string }> = {
  connected: { kind: "success", label: "Connected" },
  not_configured: { kind: "idle", label: "Not configured" },
  degraded: { kind: "waiting", label: "Degraded" },
  down: { kind: "failed", label: "Down" },
};

export function ProviderCard({ provider }: { provider: ProviderSummary }) {
  const identity = getProviderIdentity(provider.key);
  const status = STATUS_DISPLAY[provider.status];
  const isConfigured = provider.status !== "not_configured";

  return (
    <Card accent={identity.accent} className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <TierBadge tier={provider.tier} />
        <StatusIndicator kind={status.kind} label={status.label} />
      </div>

      <div>
        <h3 className="text-sm font-semibold text-slate-100">{identity.label}</h3>
        <p className="mt-0.5 text-xs text-slate-500">{isConfigured ? provider.defaultModel : "No default model set"}</p>
      </div>

      {isConfigured ? (
        <dl className="grid grid-cols-2 gap-2 text-xs text-slate-500">
          <div>
            <dt className="text-[10px] uppercase tracking-wide">Cost / 1K</dt>
            <dd className="mt-0.5">
              <CostPill usd={provider.costPer1kInputUsd} /> in · <CostPill usd={provider.costPer1kOutputUsd} /> out
            </dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wide">Avg latency</dt>
            <dd className="mt-0.5 tabular-nums text-slate-300">{provider.avgLatencyMs ? `${provider.avgLatencyMs}ms` : "—"}</dd>
          </div>
        </dl>
      ) : (
        <p className="text-xs text-slate-600">Add an API key to activate this provider.</p>
      )}

      <Link
        to={`/ai-gateway/providers/${provider.key}`}
        className="mt-1 text-xs font-medium text-accent-primary hover:underline"
      >
        {isConfigured ? "Details →" : "Set up →"}
      </Link>
    </Card>
  );
}
