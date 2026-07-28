import { Card, PlaceholderNotice, StatusIndicator } from "../../design-system";
import { ModelRoleManagementPanel } from "../../ai-gateway/components/ModelRoleManagementPanel";
import { useGatewaySettings } from "../../ai-gateway/hooks/useGatewaySettings";

/**
 * AIGatewaySettings — /ai-gateway/settings. M8.2 (AI Gateway Backend
 * Integration): now a real, READ-ONLY projection of live Gateway
 * configuration (AI_MODE, the premium-approval gate, retry limits, the
 * capability -> provider preference table, and the capability -> local
 * model role mapping approved for M8.2's "intelligent local-model
 * routing" addendum) via `useGatewaySettings()` / GET /ai-gateway/settings.
 *
 * Settings PERSISTENCE (editing any of this) and provider configuration
 * both remain explicitly out of scope - no Save button, no form state -
 * this page reads real values, it does not let anyone change them yet.
 * See docs/architecture/ai-gateway-ux-architecture.md Section 4.9 for the
 * eventual editable design.
 */
export default function AIGatewaySettings() {
  const { data, isLoading, error } = useGatewaySettings();

  if (error) return <PlaceholderNotice kind="no-data" reason={error} />;
  if (isLoading || !data) return <p className="text-xs text-slate-500">Loading…</p>;

  return (
    <div className="flex flex-col gap-6">
      <Card className="flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-slate-100">Routing</h2>
        <dl className="grid grid-cols-2 gap-4 text-xs text-slate-500 sm:grid-cols-4">
          <div>
            <dt className="text-[10px] uppercase tracking-wide">AI mode</dt>
            <dd className="mt-0.5 text-slate-200">{data.aiMode}</dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wide">Premium approval gate</dt>
            <dd className="mt-0.5">
              <StatusIndicator
                kind={data.requirePremiumApproval ? "success" : "idle"}
                label={data.requirePremiumApproval ? "Required" : "Disabled"}
              />
            </dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wide">Max attempts / provider</dt>
            <dd className="mt-0.5 tabular-nums text-slate-200">{data.maxAttemptsPerProvider}</dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wide">Default timeout</dt>
            <dd className="mt-0.5 tabular-nums text-slate-200">{data.defaultTimeoutSeconds}s</dd>
          </div>
        </dl>
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-slate-100">Capability → Provider Preference</h2>
        <ul className="flex flex-col gap-2 text-xs">
          {Object.entries(data.capabilityProviderPreference).map(([capability, chain]) => (
            <li key={capability} className="flex items-center justify-between gap-3">
              <span className="text-slate-400">{capability}</span>
              <span className="text-slate-200">{chain.join(" → ")}</span>
            </li>
          ))}
        </ul>
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-slate-100">Local Model Roles</h2>
        <p className="text-xs text-slate-500">
          Semantic role → configured local model (app/ai_gateway/local_model_policy.py). A role with no value
          configured falls back to the &quot;research&quot; role&apos;s model.
        </p>
        <ul className="flex flex-col gap-2 text-xs">
          {Object.entries(data.localModelRoles).map(([role, model]) => (
            <li key={role} className="flex items-center justify-between gap-3">
              <span className="text-slate-400">{role}</span>
              <span className="text-slate-200">{model ?? "not configured"}</span>
            </li>
          ))}
        </ul>
        <div className="mt-2 border-t border-border-hairline pt-3">
          <p className="mb-2 text-[10px] uppercase tracking-wide text-slate-500">Capability → Role preference</p>
          <ul className="flex flex-col gap-2 text-xs">
            {Object.entries(data.capabilityLocalModelRole).map(([capability, roles]) => (
              <li key={capability} className="flex items-center justify-between gap-3">
                <span className="text-slate-400">{capability}</span>
                <span className="text-slate-200">{roles.join(" → ")}</span>
              </li>
            ))}
          </ul>
        </div>
      </Card>

      <ModelRoleManagementPanel />

      <PlaceholderNotice
        kind="not-implemented"
        reason="Editing routing mode, provider priority, and cost limits is designed (see docs/architecture/ai-gateway-ux-architecture.md Section 4.9) but not yet implemented. Model Role overrides above (M8.3 Step 3) and Provider Configuration (see each provider's detail page, M8.3 Step 2) are the two settings surfaces implemented so far."
      />
    </div>
  );
}
