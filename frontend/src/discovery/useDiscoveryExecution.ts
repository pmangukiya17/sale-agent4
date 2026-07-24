import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "../api/client";
import { useInterval } from "../hooks/useInterval";
import { useEventStream } from "../realtime/useEventStream";
import type {
  WorkflowExecutionMetric,
  WorkflowExecutionViewProps,
  WorkflowStage,
} from "../components/WorkflowExecutionView";

/**
 * useDiscoveryExecution — the Discovery-specific adapter feeding the
 * generic WorkflowExecutionView (M8.8). This is where every
 * Discovery-only assumption below lives, deliberately kept OUT of the
 * view component itself so a future domain (Research/Personalization/
 * Outreach/Reply Intelligence) can write its own equivalent adapter
 * without touching WorkflowExecutionView at all.
 *
 * Mirrors app/schemas/discovery_job.py's DiscoveryJobRead field-for-field
 * (same "frontend type mirrors the backend read schema exactly"
 * discipline as useAgentActivities.ts/useNotifications.ts elsewhere in
 * this codebase).
 *
 * DiscoveryJob does not exist yet the instant "Start Discovery" is
 * clicked (see app/api/routes/discovery_searches.py's run_search() - it
 * only publishes a trigger event and returns "queued"). This hook copes
 * with that honestly: `job` starts null, `overallStatus` starts
 * "queued", and every stage renders "pending" until the Event Dispatcher
 * + Step Runner workers actually produce a real DiscoveryJob row - there
 * is no synthetic/optimistic job object invented here.
 *
 * Real-time updates: polls GET .../discovery-jobs?discovery_search_id=
 * {searchId} every 3s as a safety net (matches useNotifications.ts's own
 * "poll + stream nudge" shape), and additionally subscribes to the
 * platform's live Event stream purely as a low-latency "something
 * changed, go re-fetch" signal - it never interprets a StreamedEvent's
 * payload as the source of truth, exactly like every other M8.6 consumer
 * in this codebase. Polling stops once the job reaches a terminal status.
 */

interface DiscoveryJobProviderRun {
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

interface DiscoveryJob {
  id: string;
  discovery_search_id: string;
  status: "pending" | "running" | "completed" | "partially_completed" | "failed" | "cancelled";
  started_at: string | null;
  finished_at: string | null;
  providers_used: string[];
  raw_result_count: number;
  prospect_created_count: number;
  prospect_matched_count: number;
  prospect_qualified_count: number;
  prospect_rejected_count: number;
  error_message: string | null;
  provider_runs: DiscoveryJobProviderRun[];
}

const POLL_INTERVAL_MS = 3_000;
const STREAM_REFRESH_DEBOUNCE_MS = 500;

const TERMINAL_JOB_STATUSES = new Set(["completed", "partially_completed", "failed", "cancelled"]);

// Exported (M2 Phase 2 UX follow-up) - Prospects.tsx and
// DiscoveryJobs.tsx both need the exact same "unrecognized provider_key
// still renders sensibly" fallback for their own provider badges,
// rather than each maintaining a second copy of this title-casing
// logic. Deliberately no hardcoded provider name map beyond light
// cosmetics - an unrecognized future provider_key still renders
// (title-cased, underscores as spaces) rather than being silently
// dropped, per Principle 5 ("dynamic providers... render them
// dynamically"). Callers that have a REAL display name available (e.g.
// from GET /discovery-providers' own `name` field) should prefer that
// over this fallback - this exists specifically for the case where only
// a bare provider_key is on hand (a Prospect's `sources`, a
// DiscoveryJobProviderRun with no accompanying provider list fetched).
export function providerLabel(providerKey: string): string {
  return providerKey
    .split("_")
    .map((part) => (part.length > 0 ? part[0].toUpperCase() + part.slice(1) : part))
    .join(" ");
}

function buildStages(providerKeys: string[], job: DiscoveryJob | null): WorkflowStage[] {
  if (providerKeys.length === 0) return [];

  const runByProvider = new Map((job?.provider_runs ?? []).map((run) => [run.provider_key, run]));
  // Providers execute sequentially, in provider_keys order (see
  // app/discovery/pipeline.py's own `for provider_key in
  // search.provider_keys` loop) - the first provider_key with no
  // provider_runs row yet, WHILE the job itself is still RUNNING, is the
  // one genuinely executing right now. This is a real, documented
  // inference from the pipeline's known sequential execution, not a
  // fabricated progress indicator.
  const jobIsRunning = job?.status === "running";
  let runningAssigned = false;

  return providerKeys.map((providerKey) => {
    const run = runByProvider.get(providerKey);
    let status: WorkflowStage["status"];
    let detail: string | undefined;

    if (run) {
      status = run.status === "failed" ? "failed" : "completed";
      const parts: string[] = [];
      if (run.duration_ms != null) parts.push(`${run.duration_ms}ms`);
      parts.push(`${run.request_count} req`);
      if (run.api_cost != null) parts.push(`$${run.api_cost}`);
      if (run.token_usage != null) parts.push(`${run.token_usage} tok`);
      if (run.error_message) parts.push(run.error_message);
      detail = parts.join(" · ");
    } else if (jobIsRunning && !runningAssigned) {
      status = "running";
      runningAssigned = true;
    } else {
      status = "pending";
    }

    return { key: providerKey, label: providerLabel(providerKey), status, detail };
  });
}

function buildMetrics(job: DiscoveryJob | null): WorkflowExecutionMetric[] {
  if (!job) return [];
  return [
    { label: "Companies found", value: job.prospect_created_count + job.prospect_matched_count, tone: "info" },
    { label: "Qualified buyers", value: job.prospect_qualified_count, tone: "success" },
    { label: "Rejected buyers", value: job.prospect_rejected_count, tone: "neutral" },
  ];
}

function buildCompletionSummary(job: DiscoveryJob | null): string | null {
  if (!job || !TERMINAL_JOB_STATUSES.has(job.status)) return null;
  const found = job.prospect_created_count + job.prospect_matched_count;
  if (job.status === "failed") {
    return `Discovery failed. ${job.error_message ?? ""}`.trim();
  }
  const qualifier = job.status === "partially_completed" ? "Partially completed" : "Completed";
  return `${qualifier} — ${found} compan${found === 1 ? "y" : "ies"} found, ${job.prospect_qualified_count} qualified, ${job.prospect_rejected_count} rejected.`;
}

export function useDiscoveryExecution(companyId: string | undefined, searchId: string | undefined, providerKeys: string[]) {
  const [job, setJob] = useState<DiscoveryJob | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nowTick, setNowTick] = useState(() => Date.now());

  const refresh = useCallback(() => {
    if (!companyId || !searchId) return;
    apiClient
      .get<DiscoveryJob[]>(`/company-profiles/${companyId}/discovery-jobs`, { params: { discovery_search_id: searchId } })
      .then((res) => {
        // Backend orders by created_at desc - the first entry is the
        // latest run for this search.
        setJob(res.data.length > 0 ? res.data[0] : null);
        setError(null);
      })
      .catch(() => setError("Could not load this search's execution state."))
      .finally(() => setIsLoading(false));
  }, [companyId, searchId]);

  useEffect(refresh, [refresh]);

  const isTerminal = job != null && TERMINAL_JOB_STATUSES.has(job.status);
  useInterval(refresh, isTerminal ? null : POLL_INTERVAL_MS);

  // M8.6 real-time nudge - same debounced "arrival means re-fetch, never
  // interpret payload" shape as useNotifications.ts.
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

  // Ticks the elapsed-time display once a second while running - a real
  // duration between two real timestamps, re-rendered more often, never
  // an invented progress value (see WorkflowExecutionView's own docstring).
  useInterval(() => setNowTick(Date.now()), isTerminal ? null : 1000);

  // Explicit mapping over every real DiscoveryJobStatus value (not a
  // blind cast) - "pending"/"cancelled" have no distinct visual in
  // WorkflowExecutionView's own vocabulary, so they map to their closest
  // honest equivalent ("queued"/"failed") rather than being silently
  // passed through as an unrecognized status string.
  const JOB_STATUS_TO_OVERALL: Record<DiscoveryJob["status"], WorkflowExecutionViewProps["overallStatus"]> = {
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
      stages: buildStages(providerKeys, job),
      metrics: buildMetrics(job),
      startedAt,
      finishedAt,
      elapsedSeconds,
      // No etaSeconds - the backend has no timing model to derive one
      // from yet (see this hook's own module docstring / Principle 4).
      etaSeconds: null,
      errorMessage: job?.error_message ?? null,
      completionSummary: buildCompletionSummary(job),
    } satisfies Omit<WorkflowExecutionViewProps, "title" | "subtitle" | "resultsAction">,
  };
}
