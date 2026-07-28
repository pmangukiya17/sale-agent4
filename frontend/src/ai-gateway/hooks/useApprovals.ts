import { useCallback, useEffect, useState } from "react";
import { useGatewayDataProvider } from "../providers/GatewayDataProviderContext";
import type { ApprovalRequest } from "../types";

/**
 * useApprovals — Premium Approval Center data. Read-only in this
 * milestone: no Approve/Reject execution is wired (approval workflow is
 * explicitly out of scope) - the page consuming this hook surfaces a
 * Toast rather than mutating this list. See ApprovalCard.tsx's docstring.
 */
export function useApprovals() {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<ApprovalRequest[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setIsLoading(true);
    setError(null);
    provider
      .listApprovals()
      .then(setData)
      .catch(() => setError("Could not load pending approvals."))
      .finally(() => setIsLoading(false));
  }, [provider]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, isLoading, error, refresh };
}
