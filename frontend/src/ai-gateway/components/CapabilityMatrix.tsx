import { Check, X } from "lucide-react";
import { getProviderIdentity } from "../identity/providerIdentity";
import type { ProviderSummary } from "../types";

/**
 * CapabilityMatrix — (placeholder, per the approved M8.1 scope) a minimal
 * provider × capability grid, sourced from real mock `ProviderSummary.
 * capabilities` data rather than an invented illustration. Used on the
 * Gateway Health page shell this milestone; the fuller version (Section
 * 4.8 of the approved architecture doc - failover events, routing
 * statistics, diagnostics warnings alongside it) is explicitly deferred,
 * per that page's own PlaceholderNotice.
 *
 * Never/always renders a check or cross (never color alone) - reuses the
 * same "state = icon + color" discipline `StatusIndicator` establishes
 * elsewhere, applied to a grid cell instead of an inline label.
 */
const CAPABILITY_LABELS: Record<string, string> = {
  structured_output: "Structured output",
  tool_calling: "Tool calling",
  streaming: "Streaming",
  vision: "Vision",
  reasoning_support: "Reasoning",
};

export function CapabilityMatrix({ providers }: { providers: ProviderSummary[] }) {
  const capabilityKeys = Object.keys(CAPABILITY_LABELS);

  return (
    <div className="overflow-auto rounded-card border border-border-hairline">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th className="border-b border-border-hairline px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
              Capability
            </th>
            {providers.map((provider) => (
              <th
                key={provider.key}
                className="border-b border-border-hairline px-3 py-2 text-center text-xs font-medium uppercase tracking-wide text-slate-500"
              >
                {getProviderIdentity(provider.key).label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {capabilityKeys.map((capability) => (
            <tr key={capability} className="border-b border-border-hairline last:border-0">
              <td className="px-3 py-2 text-slate-300">{CAPABILITY_LABELS[capability]}</td>
              {providers.map((provider) => {
                const supported = provider.capabilities.includes(capability);
                return (
                  <td key={provider.key} className="px-3 py-2 text-center">
                    {supported ? (
                      <Check className="mx-auto h-3.5 w-3.5 text-status-success" aria-hidden="true" />
                    ) : (
                      <X className="mx-auto h-3.5 w-3.5 text-slate-700" aria-hidden="true" />
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
