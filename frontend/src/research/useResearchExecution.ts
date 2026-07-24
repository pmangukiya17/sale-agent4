import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "../api/client";
import { useInterval } from "../hooks/useInterval";
import { useEventStream } from "../realtime/useEventStream";
import type { BadgeTone } from "../design-system";
import type { WorkflowExecutionMetric, WorkflowExecutionViewProps, WorkflowStage } from "../components/WorkflowExecutionView";

/**
 * useResearchExecution — M8.13, exact structural mirror of
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

// Exported (M2 Phase 3 observability follow-up) - ProspectResearch.tsx
// and ResearchJobs.tsx both need to render "which engine actually
// produced this analysis" from the stored AIAnalysis.model_used value
// (never from current settings.RESEARCH_ANALYSIS_ENGINE_BACKEND config -
// a historical analysis stays labeled with whatever engine really wrote
// it, even after the config is later changed). This is read-only
// observability, not a control - there is no way to change the engine
// from here.
//
// ENGINE_LABELS is a static, known-value lookup - deliberately not a
// clever regex/parser over arbitrary model id strings, matching this
// project's existing "registry/lookup table over inference" convention
// (e.g. app.discovery.providers.registry's own PROVIDER keys). Adding a
// friendlier label for a newly-observed model_used is a one-line data
// change here, never a logic change. Any model_used NOT in this table
// (i.e. any real provider/model string, since only the deterministic
// stub's marker is known in advance) falls through to a light cosmetic
// cleanup pass - title-cased, hyphens as spaces, trailing date-like
// numeric suffix dropped - so a real model id like
// "claude-sonnet-4-5-20250929" still renders as something readable
// ("Claude Sonnet 4 5") without ever hiding or misrepresenting the
// underlying stored value.
const ENGINE_LABELS: Record<string, string> = {
  "deterministic-keyword-stub": "Deterministic Engine",
};

export function engineLabel(modelUsed: string | null | undefined): string {
  if (!modelUsed) return "Unknown engine";
  if (ENGINE_LABELS[modelUsed]) return ENGINE_LABELS[modelUsed];
  return modelUsed
    .replace(/-\d{6,}$/, "")
    .split("-")
    .map((part) => (part.length > 0 ? part[0].toUpperCase() + part.slice(1) : part))
    .join(" ");
}

// Visually distinguishes "a real AI model produced this" (the "ai" tone,
// already reserved in the design system for exactly this purpose) from
// "the rule-based deterministic fallback produced this" (neutral) - pure
// observability, matches nothing about which engine is actually
// configured to run next.
export function engineBadgeTone(modelUsed: string | null | undefined): BadgeTone {
  return modelUsed && modelUsed !== "deterministic-keyword-stub" ? "ai" : "neutral";
}

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
  if (job.raw_document_count === 0) {
    // Zero documents is expected, not an error, whenever this run had
    // nothing to analyze - Research today has only one document source
    // (manual_document, i.e. pasted/uploaded text); there is no
    // automatic web-scraping provider yet. Spelling this out here
    // (rather than just "0 document(s) analyzed") is what actually
    // explains why no signals/recommendations came out of a completed
    // run, regardless of which analysis engine (deterministic or LLM)
    // was configured to run - an LLM has nothing to analyze either if no
    // documents were supplied.
    return (
      "Completed — no research documents were available to analyze, so no signals or recommendations " +
      "were generated this run. Paste research text (website copy, a news article, a catalog extract) " +
      "before running, or connect a research provider once one becomes available."
    );
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
