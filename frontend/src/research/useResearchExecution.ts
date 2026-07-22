import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "../api/client";
import { useInterval } from "../hooks/useInterval";
import { useEventStream } from "../realtime/useEventStream";
import type { WorkflowExecutionMetric, WorkflowExecutionViewProps, WorkflowStage } from "../components/WorkflowExecutionView";

/**
 * useResearchExecution — M8.10, exact structural mirror of
 * useDiscoveryExecution.ts (M8.8) - see that module's own docstring for
 * the shared reasoning (poll + M8.6 stream nudge, no fabricated ETA,
 * terminal-status detection).
 *
 * One real, disclosed difference from Discovery: DiscoverySearch persists
 * its own provider_keys, so the frontend knows the full provider list
 * before a job even exists. ResearchRequest has NO persisted provider
 * list of its own (source_types is supplied per-run, in run_input, and
 * never stored - see research_request.py's own docstring) - so there is
 * genuinely no way to know which providers will run until the first
 * ResearchJob actually appears and reports its own provider_runs. Before
 * that, this hook shows a single honest "Queued" stage rather than
 * guessing a provider list it cannot know.
 */

interface ResearchJobProviderRun {
  provider_key: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  request_count: number;
  api_cost: number | null;
  token_usage: number | null;
  error_message: string | null;
}

interface ResearchJob {
  id: string;
  research_request_id: string;
  status: "pending" | "running" | "completed" | "partially_completed" | "failed" | "cancelled";
  started_at: string | null;
  finished_at: string | null;
  sources_used: string[];
  raw_document_count: number;
  signal_count: number;
  recommendation_count: number;
  error_message: string | null;
  provider_runs: ResearchJobProviderRun[];
}

const POLL_INTERVAL_MS = 3_000;
const STREAM_REFRESH_DEBOUNCE_MS = 500;
const TERMINAL_JOB_STATUSES = new Set(["completed", "partially_completed", "failed", "cancelled"]);

function providerLabel(providerKey: string): string {
  return providerKey
    .split("_")
    .map((part) => (part.length > 0 ? part[0].toUpperCase() + part.slice(1) : part))
    .join(" ");
}

function buildStages(job: ResearchJob | null): WorkflowStage[] {
  if (!job || job.provider_runs.length === 0) {
    // Genuinely unknown until the job exists - see this module's own
    // docstring for why (no persisted provider list on ResearchRequest).
    return [
      {
        key: "queued",
        label: "Queued",
        status: job && job.status !== "pending" ? "running" : "pending",
      },
    ];
  }
  return job.provider_runs.map((run) => {
    const parts: string[] = [];
    if (run.duration_ms != null) parts.push(`${run.duration_ms}ms`);
    parts.push(`${run.request_count} req`);
    if (run.api_cost != null) parts.push(`$${run.api_cost}`);
    if (run.token_usage != null) parts.push(`${run.token_usage} tok`);
    if (run.error_message) parts.push(run.error_message);
    return {
      key: run.provider_key,
      label: providerLabel(run.provider_key),
      status: run.status === "failed" ? "failed" : "completed",
      detail: parts.join(" · "),
    } as WorkflowStage;
  });
}

function buildMetrics(job: ResearchJob | null): WorkflowExecutionMetric[] {
  if (!job) return [];
  return [
    { label: "Documents found", value: job.raw_document_count, tone: "info" },
    { label: "Signals found", value: job.signal_count, tone: "warning" },
    { label: "Recommendations", value: job.recommendation_count, tone: "success" },
  ];
}

function buildCompletionSummary(job: ResearchJob | null): string | null {
  if (!job || !TERMINAL_JOB_STATUSES.has(job.status)) return null;
  if (job.status === "failed") {
    return `Research failed. ${job.error_message ?? ""}`.trim();
  }
  const qualifier = job.status === "partially_completed" ? "Partially completed" : "Completed";
  return `${qualifier} — ${job.raw_document_count} document(s) analyzed, ${job.signal_count} signal(s) found, ${job.recommendation_count} recommendation(s) generated.`;
}

export function useResearchExecution(companyId: string | undefined, requestId: string | undefined) {
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nowTick, setNowTick] = useState(() => Date.now());

  const refresh = useCallback(() => {
    if (!companyId || !requestId) return;
    apiClient
      .get<ResearchJob[]>(`/company-profiles/${companyId}/research-jobs`, { params: { research_request_id: requestId } })
      .then((res) => {
        setJob(res.data.length > 0 ? res.data[0] : null);
        setError(null);
      })
      .catch(() => setError("Could not load this request's execution state."))
      .finally(() => setIsLoading(false));
  }, [companyId, requestId]);

  useEffect(refresh, [refresh]);

  const isTerminal = job != null && TERMINAL_JOB_STATUSES.has(job.status);
  useInterval(refresh, isTerminal ? null : POLL_INTERVAL_MS);

  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEventStream(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(refresh, STREAM_REFRESH_DEBOUNCE_MS);
  });
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  useInterval(() => setNowTick(Date.now()), isTerminal ? null : 1000);

  const JOB_STATUS_TO_OVERALL: Record<ResearchJob["status"], WorkflowExecutionViewProps["overallStatus"]> = {
    pending: "queued",
    running: "running",
    completed: "completed",
    partially_completed: "partially_completed",
    failed: "failed",
    cancelled: "failed",
  };
  const overallStatus: WorkflowExecutionViewProps["overallStatus"] = !job ? "queued" : JOB_STATUS_TO_OVERALL[job.status];

  const startedAt = job?.started_at ?? null;
  const finishedAt = job?.finished_at ?? null;
  const elapsedSeconds = startedAt
    ? ((finishedAt ? new Date(finishedAt).getTime() : nowTick) - new Date(startedAt).getTime()) / 1000
    : null;

  return {
    isLoading,
    error,
    job,
    viewProps: {
      overallStatus,
      stages: buildStages(job),
      metrics: buildMetrics(job),
      startedAt,
      finishedAt,
      elapsedSeconds,
      etaSeconds: null,
      errorMessage: job?.error_message ?? null,
      completionSummary: buildCompletionSummary(job),
    } satisfies Omit<WorkflowExecutionViewProps, "title" | "subtitle" | "resultsAction">,
  };
}
