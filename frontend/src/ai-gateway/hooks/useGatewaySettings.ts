import { useCallback, useEffect, useState } from "react";
import { useGatewayDataProvider } from "../providers/GatewayDataProviderContext";
import type { GatewaySettings } from "../types";

/**
 * useGatewaySettings — M8.2 addition. AI Settings (read-only) page data.
 * Same `{data, isLoading, error, refresh}` contract every hook in this
 * project follows - no M8.1 hook contract changes for this milestone,
 * this is a purely additive new hook backing the page that was a static
 * PlaceholderNotice shell before M8.2 (see AIGatewaySettings.tsx).
 */
export function useGatewaySettings() {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<GatewaySettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setIsLoading(true);
    setError(null);
    provider
      .getSettings()
      .then(setData)
      .catch(() => setError("Could not load AI Gateway settings."))
      .finally(() => setIsLoading(false));
  }, [provider]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, isLoading, error, refresh };
}
