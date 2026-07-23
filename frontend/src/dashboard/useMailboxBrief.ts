import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { apiClient } from "../api/client";
import { useCompanies } from "../companies/CompanyContext";

export interface MailboxBriefRecommendation {
  title: string;
  rationale: string;
  source_type: string | null;
  source_id: string | null;
}

export interface MailboxBrief {
  id: string;
  company_profile_id: string;
  generated_at: string;
  ai_provider: string;
  ai_model: string;
  summary: string;
  recommendations: MailboxBriefRecommendation[];
  statistics: Record<string, unknown>;
  requested_by_user_id: string | null;
}

/**
 * useMailboxBrief — Track C5 (dashboard-capabilities-architecture-
 * plan.md, Section 6). Backs the Mailbox Brief dashboard card. Per the
 * CEO's explicit persistence model: on load this hook only ever GETs
 * the last SAVED brief (app/api/routes/mailbox_brief.py's
 * get_mailbox_brief) - it never generates one automatically. A 404
 * ("no brief has ever been generated for this business yet") is treated
 * as a real, valid, honest state - `brief === null` - not an error;
 * every other failure sets `error`. `generate()` is the only path that
 * ever calls POST .../mailbox-brief/generate (the explicit "Generate
 * New Brief" action) and has its own `isGenerating` flag, separate from
 * the initial `isLoading` fetch, so the button can show its own
 * in-flight state without the whole card re-rendering as "Loading…".
 */
export function useMailboxBrief() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const [brief, setBrief] = useState<MailboxBrief | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!activeCompanyId) {
      setBrief(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    apiClient
      .get<MailboxBrief>(`/company-profiles/${activeCompanyId}/mailbox-brief`)
      .then((res) => setBrief(res.data))
      .catch((err) => {
        if (axios.isAxiosError(err) && err.response?.status === 404) {
          setBrief(null); // honest "nothing generated yet" - not an error
        } else {
          setError("Could not load the Mailbox Brief.");
        }
      })
      .finally(() => setIsLoading(false));
  }, [activeCompanyId]);

  const generate = useCallback(() => {
    if (!activeCompanyId) return;
    setIsGenerating(true);
    setError(null);
    apiClient
      .post<MailboxBrief>(`/company-profiles/${activeCompanyId}/mailbox-brief/generate`)
      .then((res) => setBrief(res.data))
      .catch(() => setError("Could not generate a new Mailbox Brief."))
      .finally(() => setIsGenerating(false));
  }, [activeCompanyId]);

  useEffect(() => {
    if (companiesLoading) return;
    refresh();
  }, [companiesLoading, refresh]);

  return {
    brief,
    isLoading: isLoading || companiesLoading,
    isGenerating,
    error,
    hasActiveCompany: Boolean(activeCompanyId),
    refresh,
    generate,
  };
}
