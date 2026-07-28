import { useCallback, useEffect, useState } from "react";
import { useGatewayDataProvider } from "../providers/GatewayDataProviderContext";
import type { ActivityLogEntry } from "../types";

/** useActivity — AI Activity log data. See useGatewayOverview.ts's docstring. */
export function useActivity() {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<ActivityLogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setIsLoading(true);
    setError(null);
    provider
      .listActivity()
      .then(setData)
      .catch(() => setError("Could not load AI Gateway activity."))
      .finally(() => setIsLoading(false));
  }, [provider]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, isLoading, error, refresh };
}
