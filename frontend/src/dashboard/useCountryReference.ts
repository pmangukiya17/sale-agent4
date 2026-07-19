import { useEffect, useState } from "react";
import { apiClient } from "../api/client";

/**
 * Real reference data from GET /countries (backend/app/api/routes/
 * reference_data.py, backend Country model) - name/region/default_timezone
 * only. No flag emoji field, no lat/lon, no trade/economic data exists on
 * this model - see CountryIntelligencePanel.tsx's docstring for exactly
 * which tiers this can and can't honestly back.
 */
export interface CountryReference {
  id: string;
  code: string;
  name: string;
  region: string | null;
  default_timezone: string | null;
  timezone_note: string | null;
}

export function useCountryReference() {
  const [countries, setCountries] = useState<CountryReference[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<CountryReference[]>("/countries")
      .then((res) => {
        if (!cancelled) setCountries(res.data);
      })
      .catch(() => {
        /* Reference data is a "nice to have" enrichment here - a failed
           fetch degrades the intelligence panel to fewer fields, it never
           blocks the rest of the dashboard. */
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const byName = (name: string): CountryReference | null =>
    countries.find((c) => c.name.toLowerCase() === name.trim().toLowerCase()) ?? null;

  return { countries, isLoading, byName };
}
