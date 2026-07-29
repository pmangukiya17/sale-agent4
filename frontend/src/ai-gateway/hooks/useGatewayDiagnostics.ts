import { useCallback, useEffect, useState } from "react";
import { useGatewayDataProvider } from "../providers/GatewayDataProviderContext";
import type { GatewayDiagnostics } from "../types";

/**
 * useGatewayDiagnostics — M8.3 Step 6 (AI Gateway Management & Control,
 * Gateway Diagnostics). Auto-fetch-on-mount, same contract as
 * useProviderCapabilities.ts - `GET /ai-gateway/diagnostics` is a plain
 * read (no confirmation/action step, nothing here to trigger), it just
 * happens to be admin-gated server-side (see GatewayDataProvider.ts's own
 * docstring) - a non-admin caller sees a 403, surfaced here the same way
 * `error` is for any other failed read, matching
 * ModelRoleManagementPanel.tsx's own established precedent for an
 * admin-only GET.
 */
export function useGatewayDiagnostics() {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<GatewayDiagnostics | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setIsLoading(true);
    setError(null);
    provider
      .getDiagnostics()
      .then(setData)
      .catch(() => setError("Could not load Gateway diagnostics."))
      .finally(() => setIsLoading(false));
  }, [provider]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, isLoading, error, refresh };
}
