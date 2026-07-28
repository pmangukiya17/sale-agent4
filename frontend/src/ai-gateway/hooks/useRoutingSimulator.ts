import { useCallback, useState } from "react";
import { useGatewayDataProvider } from "../providers/GatewayDataProviderContext";
import type { RoutingSimulationRequestInput, RoutingSimulationResult } from "../types";

/**
 * useRoutingSimulator — M8.3 Step 4 (AI Gateway Management & Control,
 * Routing Simulator). A manually-triggered action hook (no auto-fetch on
 * mount, same convention as `useTestConnection` in useProviderConfig.ts) -
 * a simulation only runs when the admin explicitly asks for one, never
 * automatically, and never as a side effect of merely opening the page.
 */
export function useRoutingSimulator() {
  const provider = useGatewayDataProvider();
  const [result, setResult] = useState<RoutingSimulationResult | null>(null);
  const [isSimulating, setIsSimulating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (request: RoutingSimulationRequestInput) => {
      setIsSimulating(true);
      setError(null);
      try {
        const outcome = await provider.simulateRouting(request);
        setResult(outcome);
        return outcome;
      } catch {
        setError("Could not run the routing simulation.");
        return undefined;
      } finally {
        setIsSimulating(false);
      }
    },
    [provider]
  );

  return { result, isSimulating, error, run };
}
