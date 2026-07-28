import { useCallback, useEffect, useState } from "react";
import { useGatewayDataProvider } from "../providers/GatewayDataProviderContext";
import type { ProviderCapability } from "../types";

/**
 * useProviderCapabilities — M8.3 Step 5 (AI Gateway Management & Control,
 * Provider Capability Viewer). Same auto-fetch-on-mount contract as
 * useProviders.ts (GET /ai-gateway/capabilities is a plain read, no admin
 * gate, no user-triggered action needed - see GatewayDataProvider.ts's own
 * docstring for that endpoint).
 */
export function useProviderCapabilities() {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<ProviderCapability[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setIsLoading(true);
    setError(null);
    provider
      .listProviderCapabilities()
      .then(setData)
      .catch(() => setError("Could not load provider capabilities."))
      .finally(() => setIsLoading(false));
  }, [provider]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, isLoading, error, refresh };
}
