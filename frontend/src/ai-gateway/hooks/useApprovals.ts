import { useCallback, useEffect, useState } from "react";
import { useGatewayDataProvider } from "../providers/GatewayDataProviderContext";
import type { ApprovalRequest, PremiumPreauthorization } from "../types";

/**
 * useApprovals — Premium Approval Center data.
 *
 * M8.3 Step 7 (Premium Approval UI) addition: `approve()`/`reject()` are
 * now real mutations (`GatewayDataProvider.approveRequest()`/
 * `rejectRequest()`, admin-gated server-side) - previously this hook was
 * read-only end to end and the consuming page surfaced a "not yet
 * implemented" Toast instead (see ApprovalCard.tsx's own docstring for
 * that prior state). Both mutations `refresh()` the full list afterward
 * rather than patching just the clicked row locally - `status` is
 * computed server-side from a (company, capability) grant, not the one
 * literal `AIRequestLog` row that happened to be clicked, so a single
 * decision can change `status` on OTHER rows in this same list too (see
 * ApprovalRequestRead.status's own docstring in ../types.ts) - only a
 * real refetch reflects that honestly.
 */
export function useApprovals() {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<ApprovalRequest[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isMutating, setIsMutating] = useState(false);

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

  const approve = useCallback(
    async (approvalId: string): Promise<PremiumPreauthorization> => {
      setIsMutating(true);
      try {
        const result = await provider.approveRequest(approvalId);
        await provider.listApprovals().then(setData);
        return result;
      } finally {
        setIsMutating(false);
      }
    },
    [provider]
  );

  const reject = useCallback(
    async (approvalId: string): Promise<PremiumPreauthorization> => {
      setIsMutating(true);
      try {
        const result = await provider.rejectRequest(approvalId);
        await provider.listApprovals().then(setData);
        return result;
      } finally {
        setIsMutating(false);
      }
    },
    [provider]
  );

  return { data, isLoading, error, isMutating, refresh, approve, reject };
}
