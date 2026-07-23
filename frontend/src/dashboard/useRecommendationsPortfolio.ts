import { useCallback, useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useCompanies } from "../companies/CompanyContext";

export interface PortfolioRecommendation {
  id: string;
  prospect_id: string;
  recommendation_type: string;
  title: string;
  rationale: string | null;
  confidence: number | null;
  status: string;
  prospect: { id: string; name: string };
}

/**
 * useRecommendationsPortfolio — Track C2 (dashboard-capabilities-
 * architecture-plan.md). Backs the AI Recommendations dashboard widget
 * with the new cross-portfolio endpoint (GET .../recommendations,
 * app/api/routes/recommendations.py's `list_portfolio_recommendations`)
 * rather than fetching the prospect list and firing one
 * recommendations request per prospect - the N+1 fan-out the old
 * placeholder's own docstring explicitly called out as something never
 * to quietly introduce. Mirrors useOpenConversationsCount.ts's shape
 * (own scoped hook, own `refresh`) for the same reason that hook gave:
 * a different entity with its own endpoint, not a fit for
 * useDashboardPortfolio's Prospect-shaped selectors.
 */
export function useRecommendationsPortfolio(limit = 5) {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const [recommendations, setRecommendations] = useState<PortfolioRecommendation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!activeCompanyId) {
      setRecommendations([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    apiClient
      .get<PortfolioRecommendation[]>(`/company-profiles/${activeCompanyId}/recommendations`, { params: { limit } })
      .then((res) => setRecommendations(res.data))
      .catch(() => setError("Could not load recommendations."))
      .finally(() => setIsLoading(false));
  }, [activeCompanyId, limit]);

  useEffect(() => {
    if (companiesLoading) return;
    refresh();
  }, [companiesLoading, refresh]);

  return {
    recommendations,
    isLoading: isLoading || companiesLoading,
    error,
    hasActiveCompany: Boolean(activeCompanyId),
    refresh,
  };
}
