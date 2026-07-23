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
 *
 * `status` (Executive Daily Brief UX follow-up, post-Track-C5 approval):
 * an optional pass-through to the SAME `status` query param
 * `list_portfolio_recommendations` has always accepted
 * (`status_filter: RecommendationStatus | None = Query(None, alias=
 * "status")`) - no backend change, just a param this hook never
 * exercised before. Defaults to `undefined` (every status, unchanged
 * behavior for the Command Center widget's existing callers) so this
 * addition is purely additive.
 */
export function useRecommendationsPortfolio(limit = 5, status?: "new" | "accepted" | "dismissed") {
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
      .get<PortfolioRecommendation[]>(`/company-profiles/${activeCompanyId}/recommendations`, {
        params: { limit, ...(status ? { status } : {}) },
      })
      .then((res) => setRecommendations(res.data))
      .catch(() => setError("Could not load recommendations."))
      .finally(() => setIsLoading(false));
  }, [activeCompanyId, limit, status]);

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
