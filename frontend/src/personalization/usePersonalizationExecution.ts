import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "../api/client";
import { useInterval } from "../hooks/useInterval";
import { useEventStream } from "../realtime/useEventStream";
import type { WorkflowExecutionMetric, WorkflowExecutionViewProps, WorkflowStage } from "../components/WorkflowExecutionView";

/**
 * usePersonalizationExecution — M8.14, exact structural mirror of
 * useResearchExecution.ts (M8.13) / useDiscoveryExecution.ts (M8.8) - see
 * those modules' own docstrings for the shared reasoning (poll + M8.6
 * stream nudge, no fabricated ETA, terminal-status detection).
 *
 * The simplest of the three adapters: PersonalizationJob has no
 * provider_runs/per-run fan-out at all (see personalization_job.py's own
 * docstring - "unlike DiscoveryJob/ResearchJob there is no provider_runs
 * child - Personalization has nothing to fetch, only one internal engine
 * call to make"). There is genuinely only ONE real stage to show -
 * "Synthesize strategy" - which goes pending -> running -> completed/
 * failed as the job itself transitions. Showing a fake per-provider
 * breakdown here would be fabricating stages that don't exist in this
 * domain's own execution model.
 */

interface PersonalizationJob {
  id: string;
  personalization_request_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  strategy_count: number;
}

const POLL_INTERVAL_MS = 3_000;
const STREAM_REFRESH_DEBOUNCE_MS = 500;
const TERMINAL_JOB_STATUSES = new Set(["completed", "failed", "cancelled"]);

function buildStages(job: PersonalizationJob | null): WorkflowStage[] {
  const status: WorkflowStage["status"] =
    !job || job.status === "pending"
      ? "pending"
      : job.status === "running"
        ? "running"
        : job.status === "failed" || job.status === "cancelled"
          ? "failed"
          : "completed";
  return [
    {
      key: "synthesize_strategy",
      label: "Synthesize strategy",
      status,
      detail: job && job.status === "completed" ? `${job.strategy_count} strateg${job.strategy_count === 1 ? "y" : "ies"} generated` : undefined,
    },
  ];
}

function buildMetrics(job: PersonalizationJob | null): WorkflowExecutionMetric[] {
  if (!job) return [];
  return [{ label: "Strategies generated", value: job.strategy_count, tone: "success" }];
}

function buildCompletionSummary(job: PersonalizationJob | null): string | null {
  if (!job || !TERMINAL_JOB_STATUSES.has(job.status)) return null;
  if (job.status === "failed" || job.status === "cancelled") {
    return `Strategy synthesis failed. ${job.error_message ?? ""}`.trim();
  }
  return `Completed — ${job.strategy_count} strateg${job.strategy_count === 1 ? "y" : "ies"} generated.`;
}

export function usePersonalizationExecution(companyId: string | undefined, requestId: string | undefined) {
  const [job, setJob] = useState<PersonalizationJob | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nowTick, setNowTick] = useState(() => Date.now());

  const refresh = useCallback(() => {
    if (!companyId || !requestId) return;
    apiClient
      .get<PersonalizationJob[]>(`/company-profiles/${companyId}/personalization-jobs`, {
        params: { personalization_request_id: requestId },
      })
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

  const JOB_STATUS_TO_OVERALL: Record<PersonalizationJob["status"], WorkflowExecutionViewProps["overallStatus"]> = {
    pending: "queued",
    running: "running",
    completed: "completed",
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
