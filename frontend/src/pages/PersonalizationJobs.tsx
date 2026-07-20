import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { Card, Badge, PlaceholderNotice } from "../design-system";
import type { BadgeTone } from "../design-system";

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

const STATUS_TONES: Record<string, BadgeTone> = {
  completed: "success",
  failed: "danger",
  pending: "neutral",
  running: "info",
  cancelled: "neutral",
};

/**
 * PersonalizationJobs — M8.7 Phase E2 (AI Workforce zone). Migrated in
 * place per Design Bible Section 9.2: identical fetch calls, only the
 * markup moves onto design-system tokens/primitives.
 */
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
      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Personalization Jobs</h1>
      <p className="mb-6 text-body text-slate-400">
        Every strategy-synthesis run across every prospect. Personalization reads what Discovery and Research
        already found - it never fetches anything new, so there's no raw evidence to show here.
      </p>

      {!isLoading && jobs.length === 0 && (
        <PlaceholderNotice kind="no-data" reason="No strategy has been generated yet. Trigger one from a prospect's Strategy page." />
      )}

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
                  {run?.personalization_version_created != null ? `snapshot v${run.personalization_version_created}` : ""}
                </span>
              </button>

              {isOpen && (
                <div className="mt-3 space-y-3 border-t border-border-hairline pt-3 text-sm">
                  {job.error_message && <p className="text-status-danger">{job.error_message}</p>}
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
