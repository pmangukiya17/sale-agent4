import { useCallback, useEffect, useState } from "react";
import { useGatewayDataProvider } from "../providers/GatewayDataProviderContext";
import type { RoutingDecision } from "../types";

/** useRouting — Gateway Routing page data (recent, real-shaped routing decisions). */
export function useRouting() {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<RoutingDecision[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setIsLoading(true);
    setError(null);
    provider
      .listRoutingDecisions()
      .then(setData)
      .catch(() => setError("Could not load routing decisions."))
      .finally(() => setIsLoading(false));
  }, [provider]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, isLoading, error, refresh };
}
