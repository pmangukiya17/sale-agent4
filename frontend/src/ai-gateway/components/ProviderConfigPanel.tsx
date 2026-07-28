import { useEffect, useState } from "react";
import { Button, Card, Input, PlaceholderNotice, StatusIndicator, useToast } from "../../design-system";
import { useAuth } from "../../auth/AuthContext";
import { useProviderConfig, useProviderConfigAudit, useTestConnection } from "../hooks/useProviderConfig";
import type { ProviderKey } from "../types";

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function formatFieldValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/**
 * ProviderConfigPanel — M8.3 Step 2 (AI Gateway Management & Control,
 * Provider Management). Renders inside AIGatewayProviderDetail.tsx, below
 * the existing (M8.2) read-only summary card.
 *
 * Write access (enable/disable, API key, base URL, default model, Save)
 * is gated on the CALLER's own role client-side (`useAuth().user?.role`)
 * - purely a UX courtesy, since the backend's PUT/GET .../config and
 * .../config/audit routes are independently admin-gated
 * (get_current_active_admin) regardless of what this component renders.
 * A non-admin still sees the EFFECTIVE config read-only plus Test
 * Connection, which is intentionally NOT admin-gated anywhere (see
 * POST .../test-connection's own route docstring - it never mutates
 * anything or exposes a credential).
 */
export function ProviderConfigPanel({ providerKey }: { providerKey: ProviderKey }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const { data: config, isLoading, error, isSaving, save } = useProviderConfig(providerKey);
  const { data: auditEntries, isLoading: isAuditLoading, error: auditError } = useProviderConfigAudit(
    isAdmin ? providerKey : undefined
  );
  const { result: testResult, isTesting, error: testError, run: runTest } = useTestConnection(providerKey);
  const { showToast } = useToast();

  const [enabled, setEnabled] = useState(true);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const [baseUrlInput, setBaseUrlInput] = useState("");
  const [defaultModelInput, setDefaultModelInput] = useState("");

  useEffect(() => {
    if (!config) return;
    setEnabled(config.enabled);
    setApiKeyInput("");
    setClearApiKey(false);
    setBaseUrlInput(config.baseUrl ?? "");
    setDefaultModelInput(config.defaultModel ?? "");
  }, [config]);

  if (isLoading) {
    return <div className="h-40 animate-pulse rounded-card border border-border-hairline bg-surface-1" />;
  }
  if (error || !config) {
    return <PlaceholderNotice kind="no-data" reason={error ?? "Configuration is unavailable for this provider."} />;
  }

  async function handleSave() {
    try {
      await save({
        enabled,
        apiKey: apiKeyInput || undefined,
        clearApiKey,
        baseUrl: baseUrlInput.trim() || undefined,
        clearBaseUrl: baseUrlInput.trim() === "" && Boolean(config?.baseUrl),
        defaultModel: defaultModelInput.trim() || undefined,
        clearDefaultModel: defaultModelInput.trim() === "" && Boolean(config?.defaultModel),
      });
      showToast({ message: "Provider configuration saved.", tone: "success" });
    } catch {
      showToast({ message: "Could not save this provider's configuration.", tone: "danger" });
    }
  }

  async function handleTestConnection() {
    const outcome = await runTest();
    if (outcome) {
      showToast({
        message: outcome.success ? `Connected to ${providerKey}.` : outcome.message,
        tone: outcome.success ? "success" : "danger",
      });
    } else if (testError) {
      showToast({ message: testError, tone: "danger" });
    }
  }

  return (
    <Card className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-100">Provider Configuration</h3>
        {!isAdmin && <span className="text-[11px] text-slate-500">Read-only (admin required to edit)</span>}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={enabled}
            disabled={!isAdmin}
            onChange={(e) => setEnabled(e.target.checked)}
            className="h-4 w-4 rounded border-border-hairline bg-surface-2 accent-accent-primary disabled:cursor-not-allowed disabled:opacity-50"
          />
          Enabled
        </label>

        <div>
          <label className="text-[10px] uppercase tracking-wide text-slate-500">API key</label>
          <Input
            type="password"
            placeholder={config.hasApiKey ? "•••••••• (leave blank to keep current)" : "Not set"}
            value={apiKeyInput}
            disabled={!isAdmin || clearApiKey}
            onChange={(e) => setApiKeyInput(e.target.value)}
            className="mt-1"
          />
          {isAdmin && config.hasApiKey && (
            <label className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-500">
              <input
                type="checkbox"
                checked={clearApiKey}
                onChange={(e) => setClearApiKey(e.target.checked)}
                className="h-3 w-3 rounded border-border-hairline bg-surface-2 accent-status-danger"
              />
              Clear stored key (revert to .env)
            </label>
          )}
        </div>

        <div>
          <label className="text-[10px] uppercase tracking-wide text-slate-500">Base URL</label>
          <Input
            placeholder="e.g. http://localhost:11434/v1"
            value={baseUrlInput}
            disabled={!isAdmin}
            onChange={(e) => setBaseUrlInput(e.target.value)}
            className="mt-1"
          />
        </div>

        <div>
          <label className="text-[10px] uppercase tracking-wide text-slate-500">Default model</label>
          <Input
            placeholder="e.g. llama3.1:8b"
            value={defaultModelInput}
            disabled={!isAdmin}
            onChange={(e) => setDefaultModelInput(e.target.value)}
            className="mt-1"
          />
        </div>
      </div>

      <p className="text-[11px] text-slate-500">
        Last updated {formatDateTime(config.updatedAt)}
        {config.updatedByUserEmail ? ` by ${config.updatedByUserEmail}` : ""}. Clearing a field reverts it to the
        deployment's own .env value.
      </p>

      <div className="flex flex-wrap items-center gap-3 border-t border-border-hairline pt-4">
        {isAdmin && (
          <Button size="sm" onClick={handleSave} isLoading={isSaving}>
            Save configuration
          </Button>
        )}
        <Button size="sm" variant="secondary" onClick={handleTestConnection} isLoading={isTesting}>
          Test connection
        </Button>
        {testResult && (
          <StatusIndicator
            kind={testResult.success ? "success" : "failed"}
            label={
              testResult.success
                ? `Connected${testResult.latencyMs ? ` · ${Math.round(testResult.latencyMs)}ms` : ""}`
                : testResult.message
            }
          />
        )}
      </div>

      {testResult?.success && testResult.availableModels && testResult.availableModels.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-wide text-slate-500">Available models</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {testResult.availableModels.slice(0, 12).map((model) => (
              <span key={model} className="rounded-pill border border-border-hairline bg-surface-2 px-2 py-0.5 text-[11px] text-slate-300">
                {model}
              </span>
            ))}
          </div>
        </div>
      )}

      {isAdmin && (
        <div className="border-t border-border-hairline pt-4">
          <p className="mb-2 text-[10px] uppercase tracking-wide text-slate-500">Configuration history</p>
          {isAuditLoading ? (
            <p className="text-xs text-slate-500">Loading…</p>
          ) : auditError ? (
            <p className="text-xs text-status-danger">{auditError}</p>
          ) : auditEntries.length === 0 ? (
            <p className="text-xs text-slate-500">No changes have been recorded for this provider yet.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {auditEntries.map((entry) => (
                <li key={entry.id} className="rounded-lg border border-border-hairline bg-surface-2 p-2.5 text-xs">
                  <div className="flex items-center justify-between text-slate-400">
                    <span>{formatDateTime(entry.changedAt)}</span>
                    <span>{entry.changedByUserEmail ?? "Unknown user"}</span>
                  </div>
                  <ul className="mt-1.5 flex flex-col gap-0.5 text-slate-300">
                    {Object.entries(entry.fieldChanges).map(([field, change]) => (
                      <li key={field}>
                        <span className="text-slate-500">{field}:</span> {formatFieldValue(change.old)} → {formatFieldValue(change.new)}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
