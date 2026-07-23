import { useCallback, useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useCompanies } from "../companies/CompanyContext";

export interface OpportunityFunnelStage {
  stage: string;
  count: number;
  conversion_rate_from_previous: number | null;
}

/**
 * useOpportunityFunnel — Track C4 (dashboard-capabilities-architecture-
 * plan.md, Sections 2-3). Backs BOTH Sales Pipeline (stage-box counts
 * only) and Pipeline Overview (also reads conversion_rate_from_previous)
 * from the single shared GET .../opportunities/funnel endpoint Track C3
 * built - the same "one endpoint, two frontend granularities" call the
 * architecture doc's own Section 3.4 makes explicitly, since this is the
 * same underlying data at two presentation levels, not two unrelated
 * capabilities. No new backend surface for either widget - see
 * app.opportunities.service.compute_funnel's own docstring for the
 * conversion-rate math itself.
 */
export function useOpportunityFunnel() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const [funnel, setFunnel] = useState<OpportunityFunnelStage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!activeCompanyId) {
      setFunnel([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    apiClient
      .get<OpportunityFunnelStage[]>(`/company-profiles/${activeCompanyId}/opportunities/funnel`)
      .then((res) => setFunnel(res.data))
      .catch(() => setError("Could not load the opportunity pipeline."))
      .finally(() => setIsLoading(false));
  }, [activeCompanyId]);

  useEffect(() => {
    if (companiesLoading) return;
    refresh();
  }, [companiesLoading, refresh]);

  return {
    funnel,
    isLoading: isLoading || companiesLoading,
    error,
    hasActiveCompany: Boolean(activeCompanyId),
    refresh,
  };
}
