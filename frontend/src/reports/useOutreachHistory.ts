import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useCompanies } from "../companies/CompanyContext";

/**
 * useOutreachHistory — M8.9 Reports. Outreach is the one domain with NO
 * existing page consuming its job/run history endpoints today (confirmed:
 * ProspectOutreach.tsx only calls outreach-playbooks/outreach-requests/
 * outreach-drafts, never outreach-jobs or outreach-runs) - this is the
 * genuine gap Reports fills, not a re-implementation of something that
 * already exists elsewhere (see Reports.tsx's own docstring for why
 * Discovery/Research/Personalization/Delivery are instead just linked to
 * their existing dedicated pages rather than duplicated here).
 *
 * Same "fetch jobs + runs, join client-side by job id" pattern
 * DiscoveryJobs.tsx/ResearchJobs.tsx already established - real,
 * already-existing endpoints, nothing new on the backend. Prospect names
 * are joined in from the already-existing GET /prospects list so rows
 * show a real name instead of a bare UUID; prospect_contact_id has no
 * equivalent list endpoint to join against, so it's left as a raw id in
 * the detail view rather than guessing a display name.
 */

export interface OutreachJob {
  id: string;
  outreach_request_id: string;
  prospect_id: string;
  prospect_contact_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
}

export interface OutreachRun {
  id: string;
  outreach_job_id: string;
  prospect_id: string;
  prospect_contact_id: string;
  triggered_at: string;
  config_snapshot: Record<string, unknown>;
  outreach_draft_version_created: number | null;
}

interface ProspectLike {
  id: string;
  name: string;
}

export function useOutreachHistory() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const [jobs, setJobs] = useState<OutreachJob[]>([]);
  const [runsByJobId, setRunsByJobId] = useState<Record<string, OutreachRun>>({});
  const [prospectNameById, setProspectNameById] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (companiesLoading) return;
    if (!activeCompanyId) {
      setJobs([]);
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    Promise.all([
      apiClient.get<OutreachJob[]>(`/company-profiles/${activeCompanyId}/outreach-jobs`),
      apiClient.get<OutreachRun[]>(`/company-profiles/${activeCompanyId}/outreach-runs`),
      apiClient.get<ProspectLike[]>(`/company-profiles/${activeCompanyId}/prospects`),
    ])
      .then(([jobsRes, runsRes, prospectsRes]) => {
        if (cancelled) return;
        setJobs(jobsRes.data);
        const runMap: Record<string, OutreachRun> = {};
        for (const run of runsRes.data) runMap[run.outreach_job_id] = run;
        setRunsByJobId(runMap);
        const nameMap: Record<string, string> = {};
        for (const p of prospectsRes.data) nameMap[p.id] = p.name;
        setProspectNameById(nameMap);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load outreach history.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeCompanyId, companiesLoading]);

  return { jobs, runsByJobId, prospectNameById, isLoading: isLoading || companiesLoading, error, hasActiveCompany: Boolean(activeCompanyId) };
}
