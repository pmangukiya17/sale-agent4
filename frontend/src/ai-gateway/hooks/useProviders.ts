import { useCallback, useEffect, useState } from "react";
import { useGatewayDataProvider } from "../providers/GatewayDataProviderContext";
import type { ProviderKey, ProviderSummary } from "../types";

/**
 * useProviders — AI Providers grid data (all 6 providers). See
 * useGatewayOverview.ts's docstring for the shared contract/provider-
 * abstraction rationale; identical shape here.
 */
export function useProviders() {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<ProviderSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setIsLoading(true);
    setError(null);
    provider
      .listProviders()
      .then(setData)
      .catch(() => setError("Could not load AI providers."))
      .finally(() => setIsLoading(false));
  }, [provider]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, isLoading, error, refresh };
}

/**
 * useProvider — single-provider variant for Provider Details
 * (/ai-gateway/providers/:providerKey). Kept as its own hook rather than
 * having the page filter useProviders()' full list client-side, so a
 * future real ApiGatewayProvider can serve this from a dedicated
 * single-resource endpoint instead of always fetching all 6.
 */
export function useProvider(key: ProviderKey | undefined) {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<ProviderSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!key) {
      setData(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    provider
      .getProvider(key)
      .then(setData)
      .catch(() => setError("Could not load this provider."))
      .finally(() => setIsLoading(false));
  }, [provider, key]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, isLoading, error, refresh };
}
