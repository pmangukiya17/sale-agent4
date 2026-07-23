import { useCallback, useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useCompanies } from "../companies/CompanyContext";

export interface OpportunityCurrencyPipelineValue {
  currency: string | null;
  open_pipeline_value: number;
  closed_won_value: number;
}

/**
 * useOpportunityPipelineValue — Track C4 (dashboard-capabilities-
 * architecture-plan.md, Section 4). Backs the Revenue Pipeline KPI card
 * from GET .../opportunities/pipeline-value, which returns one row PER
 * CURRENCY actually in use - the Track C4 fix that resolves the
 * architecture doc's own Section 4.10, explicitly deferred at Track C3
 * time ("SUM(amount) across mixed currencies is meaningless without
 * conversion... this should be settled during Track C3's own review, not
 * discovered as a bug after ship"). This hook does not blend the
 * breakdown into one number itself - RevenuePipelineWidget/KpiStrip's own
 * rendering decides how to present a single-currency vs. mixed-currency
 * business, since collapsing this into one field here would silently
 * reintroduce the exact bug this fix exists to prevent.
 */
export function useOpportunityPipelineValue() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const [breakdown, setBreakdown] = useState<OpportunityCurrencyPipelineValue[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!activeCompanyId) {
      setBreakdown([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    apiClient
      .get<OpportunityCurrencyPipelineValue[]>(`/company-profiles/${activeCompanyId}/opportunities/pipeline-value`)
      .then((res) => setBreakdown(res.data))
      .catch(() => setError("Could not load pipeline value."))
      .finally(() => setIsLoading(false));
  }, [activeCompanyId]);

  useEffect(() => {
    if (companiesLoading) return;
    refresh();
  }, [companiesLoading, refresh]);

  return {
    breakdown,
    isLoading: isLoading || companiesLoading,
    error,
    hasActiveCompany: Boolean(activeCompanyId),
    refresh,
  };
}
