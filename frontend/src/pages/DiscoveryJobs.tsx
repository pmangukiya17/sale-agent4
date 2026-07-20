import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Card, Badge, PlaceholderNotice } from "../design-system";
import type { BadgeTone } from "../design-system";

interface DiscoveryJobProviderRun {
  provider_key: string;
  status: string;
  duration_ms: number | null;
  request_count: number;
  api_cost: number | null;
  token_usage: number | null;
  error_message: string | null;
}

interface DiscoveryJob {
  id: string;
  discovery_search_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  raw_result_count: number;
  prospect_created_count: number;
  prospect_matched_count: number;
  error_message: string | null;
  provider_runs: DiscoveryJobProviderRun[];
}

interface DiscoveryRun {
  id: string;
  discovery_job_id: string;
  triggered_at: string;
  config_snapshot: Record<string, unknown>;
  prospects_found_count: number;
  new_prospects_count: number;
  duplicate_count: number;
}

const STATUS_TONES: Record<string, BadgeTone> = {
  completed: "success",
  partially_completed: "warning",
  failed: "danger",
  pending: "neutral",
  running: "info",
  cancelled: "neutral",
};

/**
 * DiscoveryJobs — M8.7 Phase E2 (AI Workforce zone). Migrated in place per
 * Design Bible Section 9.2: identical fetch calls, only the markup moves
 * onto design-system tokens/primitives (Card, Badge, PlaceholderNotice).
 */
export default function DiscoveryJobs() {
  const { companyId } = useParams();
  const [jobs, setJobs] = useState<DiscoveryJob[]>([]);
  const [runsByJobId, setRunsByJobId] = useState<Record<string, DiscoveryRun>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    setIsLoading(true);
    Promise.all([
      apiClient.get(`/company-profiles/${companyId}/discovery-jobs`),
      apiClient.get(`/company-profiles/${companyId}/discovery-runs`),
    ]).then(([jobsRes, runsRes]) => {
      setJobs(jobsRes.data);
      const map: Record<string, DiscoveryRun> = {};
      for (const run of runsRes.data as DiscoveryRun[]) map[run.discovery_job_id] = run;
      setRunsByJobId(map);
      setIsLoading(false);
    });
  }, [companyId]);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Businesses", to: "/businesses" }, { label: "Discovery Jobs" }]} />

      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Discovery Jobs</h1>
      <p className="mb-6 text-body text-slate-400">
        Every past run, with per-provider metrics and the exact configuration that produced its results.
      </p>

      {!isLoading && jobs.length === 0 && <PlaceholderNotice kind="no-data" reason="No searches have been run yet." />}

      <div className="space-y-3">
        {isLoading &&
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="h-16 animate-pulse">
              {null}
            </Card>
          ))}

        {jobs.map((job) => {
          const run = runsByJobId[job.id];
          const isOpen = expandedId === job.id;
          return (
            <Card key={job.id}>
              <button className="flex w-full items-center justify-between text-left" onClick={() => setExpandedId(isOpen ? null : job.id)}>
                <div className="flex items-center gap-2">
                  <Badge tone={STATUS_TONES[job.status] ?? "neutral"}>{job.status}</Badge>
                  <span className="text-sm text-slate-200">
                    {job.started_at ? new Date(job.started_at).toLocaleString() : "—"}
                  </span>
                </div>
                <span className="text-xs text-slate-500">
                  {job.raw_result_count} raw · {job.prospect_created_count} new · {job.prospect_matched_count} re-seen
                </span>
              </button>

              {isOpen && (
                <div className="mt-3 space-y-3 border-t border-border-hairline pt-3 text-sm">
                  {job.error_message && <p className="text-status-danger">{job.error_message}</p>}
                  <div>
                    <p className="mb-1 font-medium text-slate-200">Provider execution</p>
                    {job.provider_runs.map((pr, i) => (
                      <div key={i} className="flex justify-between text-xs text-slate-400">
                        <span>{pr.provider_key} — {pr.status}</span>
                        <span>
                          {pr.duration_ms != null ? `${pr.duration_ms}ms` : ""} · {pr.request_count} req
                          {pr.api_cost != null ? ` · $${pr.api_cost}` : ""}
                          {pr.token_usage != null ? ` · ${pr.token_usage} tok` : ""}
                        </span>
                      </div>
                    ))}
                  </div>
                  {run && (
                    <div>
                      <p className="mb-1 font-medium text-slate-200">Configuration used</p>
                      <pre className="overflow-x-auto rounded-lg bg-surface-2 p-2 text-xs text-slate-300">
                        {JSON.stringify(run.config_snapshot, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
