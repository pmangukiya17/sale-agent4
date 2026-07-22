import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useCompanies } from "../companies/CompanyContext";

/**
 * useAnalytics — M8.9. Every number this hook produces comes from an
 * already-existing, already-shipped backend endpoint (the same ones
 * DiscoveryJobs.tsx/ResearchJobs.tsx/PersonalizationJobs.tsx/
 * DeliveryCampaigns.tsx already call) - per the approved M8.9 scope, this
 * milestone adds ZERO new backend routes/aggregation. Status counts and
 * average durations below are computed client-side over the real rows
 * these endpoints return, the same "pure aggregation over already-fetched
 * data" discipline dashboard/selectors.ts already established for
 * Command Center.
 *
 * Deliberately does NOT fetch Delivery queue-items here - a campaign's
 * sent/failed/pending breakdown is fetched lazily, per-campaign, only
 * when a user actually opens it (see useCampaignQueueStats below) rather
 * than N+1-fetching every campaign's full queue on page load.
 */

export interface JobLike {
  status: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobHealthSummary {
  total: number;
  countsByStatus: Record<string, number>;
  /** null when no job in this domain has both started_at and finished_at yet - never a fabricated 0. */
  avgDurationMs: number | null;
}

export function summarizeJobs(jobs: JobLike[]): JobHealthSummary {
  const countsByStatus: Record<string, number> = {};
  const durations: number[] = [];
  for (const job of jobs) {
    countsByStatus[job.status] = (countsByStatus[job.status] ?? 0) + 1;
    if (job.started_at && job.finished_at) {
      durations.push(new Date(job.finished_at).getTime() - new Date(job.started_at).getTime());
    }
  }
  return {
    total: jobs.length,
    countsByStatus,
    avgDurationMs: durations.length > 0 ? durations.reduce((a, b) => a + b, 0) / durations.length : null,
  };
}

export interface DeliveryCampaignSummary {
  id: string;
  name: string;
  status: string;
}

interface AnalyticsData {
  discovery: JobHealthSummary;
  research: JobHealthSummary;
  personalization: JobHealthSummary;
  outreach: JobHealthSummary;
  campaigns: DeliveryCampaignSummary[];
}

const EMPTY_SUMMARY: JobHealthSummary = { total: 0, countsByStatus: {}, avgDurationMs: null };

export function useAnalytics() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (companiesLoading) return;
    if (!activeCompanyId) {
      setData(null);
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    Promise.all([
      apiClient.get<JobLike[]>(`/company-profiles/${activeCompanyId}/discovery-jobs`),
      apiClient.get<JobLike[]>(`/company-profiles/${activeCompanyId}/research-jobs`),
      apiClient.get<JobLike[]>(`/company-profiles/${activeCompanyId}/personalization-jobs`),
      apiClient.get<JobLike[]>(`/company-profiles/${activeCompanyId}/outreach-jobs`),
      apiClient.get<DeliveryCampaignSummary[]>(`/company-profiles/${activeCompanyId}/delivery-campaigns`),
    ])
      .then(([discoveryRes, researchRes, personalizationRes, outreachRes, campaignsRes]) => {
        if (cancelled) return;
        setData({
          discovery: summarizeJobs(discoveryRes.data),
          research: summarizeJobs(researchRes.data),
          personalization: summarizeJobs(personalizationRes.data),
          outreach: summarizeJobs(outreachRes.data),
          campaigns: campaignsRes.data,
        });
      })
      .catch(() => {
        if (!cancelled) setError("Could not load analytics data.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeCompanyId, companiesLoading]);

  return {
    data: data ?? { discovery: EMPTY_SUMMARY, research: EMPTY_SUMMARY, personalization: EMPTY_SUMMARY, outreach: EMPTY_SUMMARY, campaigns: [] },
    isLoading: isLoading || companiesLoading,
    error,
    hasActiveCompany: Boolean(activeCompanyId),
  };
}

interface QueueItemLike {
  status: string;
}

export interface CampaignQueueStats {
  total: number;
  sent: number;
  failed: number;
  pending: number;
}

/**
 * On-demand, per-campaign queue breakdown - fetched only when a caller
 * actually invokes this (e.g. a user expands one campaign row), never
 * eagerly for every campaign. "pending" groups every non-terminal status
 * (queued/scheduled/sending/retry) since DeliveryQueueItemStatus's own
 * finer states aren't yet part of any approved Analytics vocabulary -
 * showing sent/failed/pending only, straight from real rows.
 */
export async function fetchCampaignQueueStats(companyId: string, campaignId: string): Promise<CampaignQueueStats> {
  const res = await apiClient.get<QueueItemLike[]>(`/company-profiles/${companyId}/delivery-campaigns/${campaignId}/queue-items`);
  let sent = 0;
  let failed = 0;
  let pending = 0;
  for (const item of res.data) {
    if (item.status === "sent") sent += 1;
    else if (item.status === "failed") failed += 1;
    else pending += 1;
  }
  return { total: res.data.length, sent, failed, pending };
}
