import { useCallback, useEffect, useState } from "react";
import { useGatewayDataProvider } from "../providers/GatewayDataProviderContext";
import type { PremiumPreauthorization } from "../types";

/**
 * useApprovalHistory — M8.3 Step 7 (Premium Approval UI). Read-only, same
 * { data, isLoading, error, refresh } contract convention `useApprovals.ts`
 * already established. Admin-gated server-side (`GET /ai-gateway/approvals/history`
 * 403s for a non-admin caller, CEO decision 2026-07-29).
 *
 * `enabled` (default true) skips the fetch entirely when false - the call
 * site passes `isAdmin` here (`useAuth().user?.role`, same client-side
 * courtesy `ModelRoleManagementPanel.tsx` already establishes for its own
 * admin-only writes) so a non-admin viewing this page never fires a
 * request that's guaranteed to 403. React's rules of hooks mean this hook
 * must still be CALLED unconditionally at every render regardless of
 * role; `enabled` is how it stays a no-op instead of a doomed fetch.
 */
export function useApprovalHistory({ enabled = true }: { enabled?: boolean } = {}) {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<PremiumPreauthorization[]>([]);
  const [isLoading, setIsLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!enabled) return;
    setIsLoading(true);
    setError(null);
    provider
      .listApprovalHistory()
      .then(setData)
      .catch(() => setError("Could not load approval history."))
      .finally(() => setIsLoading(false));
  }, [provider, enabled]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, isLoading, error, refresh };
}
