import { useCallback, useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useCompanies } from "../companies/CompanyContext";

/**
 * useOpenConversationsCount — Track C1 (dashboard-capabilities-
 * architecture-plan.md). Backs the Open Conversations KPI card with the
 * real count endpoint (GET .../conversations/count?status=open,
 * app/api/routes/conversations.py) rather than fetching the full
 * conversation list just to read its length - same "aggregation belongs
 * server-side" principle useAgentActivities/useDashboardPortfolio's own
 * selectors already follow elsewhere on this dashboard. Mirrors
 * useAgentActivities.ts's shape (own scoped hook, own `refresh`) rather
 * than folding into useDashboardPortfolio, since this is a different
 * entity (Conversation, not Prospect) with its own endpoint.
 */
export function useOpenConversationsCount() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const [count, setCount] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!activeCompanyId) {
      setCount(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    apiClient
      .get<{ count: number }>(`/company-profiles/${activeCompanyId}/conversations/count`, { params: { status: "open" } })
      .then((res) => setCount(res.data.count))
      .catch(() => setError("Could not load open conversations."))
      .finally(() => setIsLoading(false));
  }, [activeCompanyId]);

  useEffect(() => {
    if (companiesLoading) return;
    refresh();
  }, [companiesLoading, refresh]);

  return {
    count,
    isLoading: isLoading || companiesLoading,
    error,
    hasActiveCompany: Boolean(activeCompanyId),
    refresh,
  };
}
