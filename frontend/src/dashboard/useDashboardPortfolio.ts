import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useCompanies } from "../companies/CompanyContext";

/**
 * Prospect — the real M1-M7 entity (Discovery/Research/Personalization/
 * Outreach all read and write this). Field list here is intentionally a
 * subset of ProspectRead: only what the M8.3 dashboard widgets actually
 * consume, not a full re-declaration of the backend schema.
 */
export interface DashboardProspect {
  id: string;
  name: string;
  country: string | null;
  status: string;
  relationship_stage: string;
  total_score: number | null;
  industry_raw: string | null;
  first_discovered_at: string;
  last_seen_at: string;
  reviewed_at: string | null;
}

/**
 * useDashboardPortfolio — single shared fetch of the active company's
 * Prospect list (GET /company-profiles/{id}/prospects), reused by every
 * Zone 1-3 widget that needs prospect-derived data (KPI strip, World Map,
 * AI Pipeline widget, Today's Priorities, Top Performing Countries,
 * Activity Timeline). One network call per dashboard load instead of one
 * per widget - this hook owns the fetch, selectors.ts owns turning the raw
 * list into each widget's shape, and the widgets themselves stay pure
 * presentation, per the milestone's "no business logic in presentation
 * components" requirement.
 *
 * No company selected → returns isLoading=false, prospects=[], and
 * hasActiveCompany=false so callers can render the same "select a
 * business" empty state every other company-scoped page already uses,
 * instead of a misleading "0 prospects" number.
 */
export function useDashboardPortfolio() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const [prospects, setProspects] = useState<DashboardProspect[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (companiesLoading) return;
    if (!activeCompanyId) {
      setProspects([]);
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    apiClient
      .get<DashboardProspect[]>(`/company-profiles/${activeCompanyId}/prospects`)
      .then((res) => {
        if (!cancelled) setProspects(res.data);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load prospects.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeCompanyId, companiesLoading]);

  return {
    prospects,
    isLoading: isLoading || companiesLoading,
    error,
    hasActiveCompany: Boolean(activeCompanyId),
  };
}

/**
 * useLegacyCompanyStages — the ORIGINAL M0 Company model (GET /companies),
 * kept deliberately separate from useDashboardPortfolio's Prospect fetch.
 * This is real data, but it is a different, older entity than Prospect -
 * see SalesPipelineWidget.tsx's docstring for why it's still the most
 * honest source for a deal-stage-shaped widget today.
 */
export interface LegacyCompany {
  id: string;
  name: string;
  country: string | null;
  stage: string;
  icp_score: number | null;
  created_at: string;
}

export function useLegacyCompanyStages() {
  const [companies, setCompanies] = useState<LegacyCompany[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<LegacyCompany[]>("/companies")
      .then((res) => {
        if (!cancelled) setCompanies(res.data);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load companies.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { companies, isLoading, error };
}
