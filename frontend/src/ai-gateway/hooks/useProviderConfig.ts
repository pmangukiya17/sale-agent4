import { useCallback, useEffect, useState } from "react";
import { useGatewayDataProvider } from "../providers/GatewayDataProviderContext";
import type { ConnectionTestResult, ProviderConfig, ProviderConfigAuditEntry, ProviderConfigWrite, ProviderKey } from "../types";

/**
 * useProviderConfig — M8.3 Step 2 (AI Gateway Management & Control,
 * Provider Management). Same shape/contract convention every other hook
 * in this folder already follows (useProviders.ts, useApprovals.ts, ...):
 * a provider-abstraction-backed { data, isLoading, error, refresh } read,
 * plus a `save()` action here since this is this package's first WRITE
 * hook. `save()` intentionally does NOT call `refresh()` afterward - the
 * backend's PUT response IS the freshly-resolved row (see
 * ApiGatewayProvider.saveProviderConfig()), so updating local state
 * directly from that response avoids a redundant second network call.
 */
export function useProviderConfig(key: ProviderKey | undefined) {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<ProviderConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const refresh = useCallback(() => {
    if (!key) {
      setData(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    provider
      .getProviderConfig(key)
      .then(setData)
      .catch(() => setError("Could not load this provider's configuration."))
      .finally(() => setIsLoading(false));
  }, [provider, key]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const save = useCallback(
    async (patch: ProviderConfigWrite): Promise<ProviderConfig> => {
      if (!key) throw new Error("No provider selected");
      setIsSaving(true);
      try {
        const updated = await provider.saveProviderConfig(key, patch);
        setData(updated);
        return updated;
      } finally {
        setIsSaving(false);
      }
    },
    [provider, key]
  );

  return { data, isLoading, error, isSaving, refresh, save };
}

/**
 * useProviderConfigAudit — the CEO's "lightweight configuration audit
 * history" requirement, read-only, most-recent-first (see the backend
 * `list_provider_config_audit()`'s own docstring - this hook just calls
 * through the provider abstraction, same as every other list hook here).
 */
export function useProviderConfigAudit(key: ProviderKey | undefined, limit = 20) {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<ProviderConfigAuditEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!key) {
      setData([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    provider
      .listProviderConfigAudit(key, limit)
      .then(setData)
      .catch(() => setError("Could not load configuration history."))
      .finally(() => setIsLoading(false));
  }, [provider, key, limit]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, isLoading, error, refresh };
}

/**
 * useTestConnection — a manually-triggered action hook (no auto-fetch on
 * mount, unlike every other hook here) since a connection test is a real,
 * human-initiated probe (see ProviderClient.test_connection()'s own
 * docstring for why this is deliberately never called automatically).
 */
export function useTestConnection(key: ProviderKey | undefined) {
  const provider = useGatewayDataProvider();
  const [result, setResult] = useState<ConnectionTestResult | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    if (!key) return;
    setIsTesting(true);
    setError(null);
    try {
      const outcome = await provider.testConnection(key);
      setResult(outcome);
      return outcome;
    } catch {
      setError("Could not run the connection test.");
      return undefined;
    } finally {
      setIsTesting(false);
    }
  }, [provider, key]);

  return { result, isTesting, error, run };
}
