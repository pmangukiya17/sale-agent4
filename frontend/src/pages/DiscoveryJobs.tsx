import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";

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

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300",
  partially_completed: "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
  pending: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
  running: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  cancelled: "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400",
};

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
      <h2 className="mb-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">Discovery Jobs</h2>
      <p className="mb-6 text-sm text-slate-500 dark:text-slate-400">
        Every past run, with per-provider metrics and the exact configuration that produced its results.
      </p>

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && jobs.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900">
          No searches have been run yet.
        </div>
      )}

      <div className="space-y-3">
        {jobs.map((job) => {
          const run = runsByJobId[job.id];
          const isOpen = expandedId === job.id;
          return (
            <div key={job.id} className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
              <button className="flex w-full items-center justify-between text-left" onClick={() => setExpandedId(isOpen ? null : job.id)}>
                <div>
                  <span className={`mr-2 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[job.status] ?? ""}`}>{job.status}</span>
                  <span className="text-sm text-slate-700 dark:text-slate-200">
                    {job.started_at ? new Date(job.started_at).toLocaleString() : "—"}
                  </span>
                </div>
                <span className="text-xs text-slate-500">
                  {job.raw_result_count} raw · {job.prospect_created_count} new · {job.prospect_matched_count} re-seen
                </span>
              </button>

              {isOpen && (
                <div className="mt-3 space-y-3 border-t border-slate-100 pt-3 text-sm dark:border-slate-700">
                  {job.error_message && <p className="text-red-600">{job.error_message}</p>}
                  <div>
                    <p className="mb-1 font-medium text-slate-700 dark:text-slate-200">Provider execution</p>
                    {job.provider_runs.map((pr, i) => (
                      <div key={i} className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
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
                      <p className="mb-1 font-medium text-slate-700 dark:text-slate-200">Configuration used</p>
                      <pre className="overflow-x-auto rounded-md bg-slate-50 p-2 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                        {JSON.stringify(run.config_snapshot, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
