import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";

interface PersonalizationJob {
  id: string;
  prospect_id: string;
  personalization_request_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
}

interface PersonalizationRun {
  id: string;
  personalization_job_id: string;
  triggered_at: string;
  config_snapshot: Record<string, unknown>;
  personalization_version_created: number | null;
}

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
  pending: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
  running: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  cancelled: "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400",
};

export default function PersonalizationJobs() {
  const { companyId } = useParams();
  const [jobs, setJobs] = useState<PersonalizationJob[]>([]);
  const [runsByJobId, setRunsByJobId] = useState<Record<string, PersonalizationRun>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    setIsLoading(true);
    Promise.all([
      apiClient.get(`/company-profiles/${companyId}/personalization-jobs`),
      apiClient.get(`/company-profiles/${companyId}/personalization-runs`),
    ]).then(([jobsRes, runsRes]) => {
      setJobs(jobsRes.data);
      const map: Record<string, PersonalizationRun> = {};
      for (const run of runsRes.data as PersonalizationRun[]) map[run.personalization_job_id] = run;
      setRunsByJobId(map);
      setIsLoading(false);
    });
  }, [companyId]);

  return (
    <div>
      <h2 className="mb-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">Personalization Jobs</h2>
      <p className="mb-6 text-sm text-slate-500 dark:text-slate-400">
        Every strategy-synthesis run across every prospect. Personalization reads what Discovery and Research
        already found - it never fetches anything new, so there's no raw evidence to show here.
      </p>

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && jobs.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900">
          No strategy has been generated yet. Trigger one from a prospect's Strategy page.
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
                  {run?.personalization_version_created != null ? `snapshot v${run.personalization_version_created}` : ""}
                </span>
              </button>

              {isOpen && (
                <div className="mt-3 space-y-3 border-t border-slate-100 pt-3 text-sm dark:border-slate-700">
                  {job.error_message && <p className="text-red-600">{job.error_message}</p>}
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
