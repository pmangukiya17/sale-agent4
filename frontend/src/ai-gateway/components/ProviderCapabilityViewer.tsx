import { Check, X } from "lucide-react";
import { Badge, Tooltip } from "../../design-system";
import { PROVIDER_IDENTITIES } from "../identity/providerIdentity";
import type { CapabilityValues, ProviderCapability, ProviderKey } from "../types";

/** A provider_key the backend returns that isn't (yet) in
 * PROVIDER_IDENTITIES falls back to its own `label` field rather than
 * throwing - keeps this table future-proof for a 7th provider registered
 * server-side before its frontend identity entry is added. */
function labelFor(p: ProviderCapability): string {
  return PROVIDER_IDENTITIES[p.providerKey as ProviderKey]?.label ?? p.label;
}

/**
 * ProviderCapabilityViewer — M8.3 Step 5 (AI Gateway Management &
 * Control, Provider Capability Viewer). Replaces the earlier
 * CapabilityMatrix placeholder (M8.1) on the Gateway Health page with a
 * richer comparison view sourced from the real, centralized capability
 * catalog (`GET /ai-gateway/capabilities` → `app.ai_gateway.capabilities`
 * via `ui_query.list_provider_capabilities()`) - every provider in
 * `PROVIDER_CLIENT_REGISTRY` is iterated generically here too (never
 * branched on by name), so a future 7th provider appears in this table
 * automatically the moment it's registered, with no second edit required.
 *
 * Two clearly separated sections, per the CEO's Step 5 requirement to
 * distinguish provider-level facts from model-specific ones:
 *
 * 1. "Provider-level capabilities" - fixed, protocol/SDK-level booleans
 *    declared once per provider (structured output, tool calling,
 *    streaming, vision, embeddings, reasoning). Each cell shows an icon
 *    AND an explicit "Supported"/"Not supported" text label - never color
 *    or icon alone - so an unsupported capability is never ambiguous.
 * 2. "Model-specific (currently configured model)" - the provider's
 *    default model plus its context/output token limits, which are
 *    per-model facts, not provider-wide ones (see
 *    app/ai_gateway/capabilities.py's own docstring for why). A provider
 *    with no configured default model shows "Not configured" rather than
 *    a fabricated number.
 *
 * A provider whose `effective` capabilities differ from its
 * `providerLevel` ones (`hasModelOverride`) gets an explicit "Model
 * override" badge on that field, with a tooltip naming the provider-level
 * default it's overriding - today this never fires for any real provider
 * (`_CAPABILITY_OVERRIDES` has zero registered entries - see
 * capabilities.py's own docstring), so every provider instead shows "Using
 * provider defaults" - an honest statement, not a placeholder.
 */
/** `overrideField` is the snake_case name the backend's `overridden_fields`
 * list uses (see app/ai_gateway/capabilities.py's `diff_capabilities()`,
 * which derives its field names from the `ProviderCapabilities` dataclass
 * directly) - kept as an explicit mapping here rather than a camelCase ->
 * snake_case string transform, since a couple of these names diverge in
 * shape (`toolCalling` -> `tool_calling`) enough that a generic regex
 * would be more fragile than just naming both forms once. */
const CAPABILITY_ROWS: { key: keyof CapabilityValues; overrideField: string; label: string }[] = [
  { key: "structuredOutput", overrideField: "structured_output", label: "Structured output" },
  { key: "toolCalling", overrideField: "tool_calling", label: "Tool calling" },
  { key: "streaming", overrideField: "streaming", label: "Streaming" },
  { key: "vision", overrideField: "vision", label: "Vision" },
  { key: "embeddings", overrideField: "embeddings", label: "Embeddings" },
  { key: "reasoningSupport", overrideField: "reasoning_support", label: "Reasoning" },
];

function CapabilityCell({
  supported,
  overridden,
  providerLevelValue,
}: {
  supported: boolean;
  overridden: boolean;
  providerLevelValue: boolean;
}) {
  const cell = (
    <div className="flex flex-col items-center gap-0.5">
      {supported ? (
        <Check className="h-3.5 w-3.5 text-status-success" aria-hidden="true" />
      ) : (
        <X className="h-3.5 w-3.5 text-slate-700" aria-hidden="true" />
      )}
      <span className={supported ? "text-[10px] text-status-success" : "text-[10px] text-slate-600"}>
        {supported ? "Supported" : "Not supported"}
      </span>
      {overridden && (
        <span className="mt-0.5 inline-block h-1.5 w-1.5 rounded-full bg-accent-ai" aria-hidden="true" />
      )}
    </div>
  );

  if (!overridden) return <td className="px-3 py-2 text-center align-top">{cell}</td>;

  return (
    <td className="px-3 py-2 text-center align-top">
      <Tooltip
        content={`Model override: provider default is "${providerLevelValue ? "supported" : "not supported"}"`}
      >
        {cell}
      </Tooltip>
    </td>
  );
}

function formatTokens(value: number | null): string {
  if (value === null) return "—";
  return value >= 1000 ? `${(value / 1000).toLocaleString()}k` : String(value);
}

export function ProviderCapabilityViewer({ providers }: { providers: ProviderCapability[] }) {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="mb-1.5 text-[10px] uppercase tracking-wide text-slate-500">
          Provider-level capabilities
        </p>
        <div className="overflow-auto rounded-card border border-border-hairline">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                <th className="border-b border-border-hairline px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                  Capability
                </th>
                {providers.map((p) => (
                  <th
                    key={p.providerKey}
                    className="border-b border-border-hairline px-3 py-2 text-center text-xs font-medium uppercase tracking-wide text-slate-500"
                  >
                    {labelFor(p)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CAPABILITY_ROWS.map((row) => (
                <tr key={row.key} className="border-b border-border-hairline last:border-0">
                  <td className="px-3 py-2 text-slate-300">{row.label}</td>
                  {providers.map((p) => (
                    <CapabilityCell
                      key={p.providerKey}
                      supported={p.effective[row.key] as boolean}
                      overridden={p.overriddenFields.includes(row.overrideField)}
                      providerLevelValue={p.providerLevel[row.key] as boolean}
                    />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <p className="mb-1.5 text-[10px] uppercase tracking-wide text-slate-500">
          Model-specific (currently configured model)
        </p>
        <div className="overflow-auto rounded-card border border-border-hairline">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                <th className="border-b border-border-hairline px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                  Provider
                </th>
                <th className="border-b border-border-hairline px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                  Default model
                </th>
                <th className="border-b border-border-hairline px-3 py-2 text-center text-xs font-medium uppercase tracking-wide text-slate-500">
                  Max context
                </th>
                <th className="border-b border-border-hairline px-3 py-2 text-center text-xs font-medium uppercase tracking-wide text-slate-500">
                  Max output
                </th>
                <th className="border-b border-border-hairline px-3 py-2 text-center text-xs font-medium uppercase tracking-wide text-slate-500">
                  Overrides
                </th>
              </tr>
            </thead>
            <tbody>
              {providers.map((p) => (
                <tr key={p.providerKey} className="border-b border-border-hairline last:border-0">
                  <td className="px-3 py-2 text-slate-300">{p.label}</td>
                  <td className="px-3 py-2 text-slate-300">
                    {p.defaultModel ?? <span className="text-slate-600">Not configured</span>}
                  </td>
                  <td className="px-3 py-2 text-center text-slate-400">{formatTokens(p.effective.maxContextTokens)}</td>
                  <td className="px-3 py-2 text-center text-slate-400">{formatTokens(p.effective.maxOutputTokens)}</td>
                  <td className="px-3 py-2 text-center">
                    {p.hasModelOverride ? (
                      <Badge tone="ai">
                        {p.overriddenFields.length} field{p.overriddenFields.length === 1 ? "" : "s"} overridden
                      </Badge>
                    ) : (
                      <span className="text-[11px] text-slate-600">Using provider defaults</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
