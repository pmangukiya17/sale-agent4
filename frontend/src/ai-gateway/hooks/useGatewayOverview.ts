import { useCallback, useEffect, useState } from "react";
import { useGatewayDataProvider } from "../providers/GatewayDataProviderContext";
import type { GatewayOverview } from "../types";

/**
 * useGatewayOverview — AI Overview page data. Same `{data, isLoading,
 * error, refresh}` contract every hook in this project follows (see
 * ai-workforce/useAgentActivities.ts), sourced from the active
 * `GatewayDataProvider` (mock today, real backend later) rather than a
 * direct `apiClient` call - this hook never imports the mock fixtures
 * itself.
 */
export function useGatewayOverview() {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<GatewayOverview | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setIsLoading(true);
    setError(null);
    provider
      .getOverview()
      .then(setData)
      .catch(() => setError("Could not load AI Gateway overview."))
      .finally(() => setIsLoading(false));
  }, [provider]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, isLoading, error, refresh };
}
