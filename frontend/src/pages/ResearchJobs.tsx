import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { Card, Badge, PlaceholderNotice } from "../design-system";
import type { BadgeTone } from "../design-system";

interface ResearchJobProviderRun {
  provider_key: string;
  status: string;
  duration_ms: number | null;
  request_count: number;
  api_cost: number | null;
  token_usage: number | null;
  error_message: string | null;
}

interface RawDocument {
  id: string;
  document_type: string;
  extracted_text: string | null;
  source_url: string | null;
}

interface ResearchSource {
  id: string;
  provider_key: string;
  status: string;
  raw_documents: RawDocument[];
}

interface AIAnalysis {
  id: string;
  analysis_type: string;
  model_used: string;
  confidence: number | null;
  reasoning: string | null;
  structured_output: Record<string, unknown>;
}

interface ResearchJob {
  id: string;
  prospect_id: string;
  research_request_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  raw_document_count: number;
  error_message: string | null;
  provider_runs: ResearchJobProviderRun[];
  sources: ResearchSource[];
  analyses: AIAnalysis[];
}

interface ResearchRun {
  id: string;
  research_job_id: string;
  triggered_at: string;
  config_snapshot: Record<string, unknown>;
  documents_found_count: number;
  intelligence_version_created: number | null;
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
 * ResearchJobs — M8.7 Phase E2 (AI Workforce zone). Migrated in place per
 * Design Bible Section 9.2: identical fetch calls, only the markup moves
 * onto design-system tokens/primitives.
 */
export default function ResearchJobs() {
  const { companyId } = useParams();
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [runsByJobId, setRunsByJobId] = useState<Record<string, ResearchRun>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    setIsLoading(true);
    Promise.all([
      apiClient.get(`/company-profiles/${companyId}/research-jobs`),
      apiClient.get(`/company-profiles/${companyId}/research-runs`),
    ]).then(([jobsRes, runsRes]) => {
      setJobs(jobsRes.data);
      const map: Record<string, ResearchRun> = {};
      for (const run of runsRes.data as ResearchRun[]) map[run.research_job_id] = run;
      setRunsByJobId(map);
      setIsLoading(false);
    });
  }, [companyId]);

  return (
    <div>
      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Research Jobs</h1>
      <p className="mb-6 text-body text-slate-400">
        Every AI Research run across every prospect - raw documents fetched, AI analyses produced, and the exact
        configuration used. Nothing here is ever discarded, even across re-runs.
      </p>

      {!isLoading && jobs.length === 0 && (
        <PlaceholderNotice kind="no-data" reason="No research has been run yet. Trigger one from a prospect's Research page." />
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
                <span className="text-xs text-slate-500">{job.raw_document_count} document(s)</span>
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

                  {job.sources.length > 0 && (
                    <div>
                      <p className="mb-1 font-medium text-slate-200">Evidence (raw documents)</p>
                      <div className="space-y-2">
                        {job.sources.flatMap((s) => s.raw_documents).map((doc) => (
                          <div key={doc.id} className="rounded-lg bg-surface-2 p-2">
                            <p className="text-xs font-medium text-slate-300">
                              {doc.document_type}{doc.source_url ? ` — ${doc.source_url}` : ""}
                            </p>
                            {doc.extracted_text && <p className="mt-1 line-clamp-3 text-xs text-slate-400">{doc.extracted_text}</p>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {job.analyses.length > 0 && (
                    <div>
                      <p className="mb-1 font-medium text-slate-200">AI analyses</p>
                      <div className="space-y-2">
                        {job.analyses.map((a) => (
                          <div key={a.id} className="rounded-lg bg-surface-2 p-2">
                            <div className="flex justify-between text-xs font-medium text-slate-300">
                              <span>{a.analysis_type.replace(/_/g, " ")}</span>
                              <span>{a.confidence != null ? `${Math.round(a.confidence * 100)}% confidence` : ""}</span>
                            </div>
                            {a.reasoning && <p className="mt-1 text-xs text-slate-400">{a.reasoning}</p>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

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
