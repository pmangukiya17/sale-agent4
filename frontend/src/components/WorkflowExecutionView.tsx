import type { ReactNode } from "react";
import { Badge, Card, StatusIndicator } from "../design-system";
import type { BadgeTone, StatusKind } from "../design-system";

/**
 * WorkflowExecutionView — M8.8 (Live AI Workflow Visualization).
 *
 * The reusable component the user's own spec required: "Do not build a
 * Discovery-only implementation... this must become the standard workflow
 * visualization component used by future AI agents across the platform."
 * Discovery is the first consumer (see frontend/src/discovery/
 * useDiscoveryExecution.ts for its adapter), but this component itself
 * knows nothing about Discovery, providers, prospects, or any other
 * domain noun - every field below is generic ("a stage", "a metric", "an
 * overall status"), the same way DiscoveryJobRead's own shape is generic
 * enough that a future Research/Personalization/Outreach/Reply
 * Intelligence job could feed this exact same component through its own,
 * differently-shaped adapter hook.
 *
 * Principle 1 ("never fake progress") in practice here: this component
 * renders EXACTLY what its props say and nothing more - it never invents
 * a percentage, timer, or stage. `etaSeconds` is only ever rendered if the
 * caller actually passes a number; there is no client-side estimation
 * logic anywhere in this file. `elapsedSeconds` is the one piece of
 * "computed" display in this component, and it is a straightforward
 * duration between two REAL timestamps the caller already fetched
 * (startedAt/finishedAt) - re-rendered every second by the caller's own
 * ticking interval, not derived from anything invented here.
 */
export type WorkflowStageStatus = "completed" | "running" | "pending" | "failed";

export interface WorkflowStage {
  key: string;
  label: string;
  status: WorkflowStageStatus;
  /** Optional short real-data line, e.g. "42 requests · 1.2s · $0.00". */
  detail?: string;
}

export interface WorkflowExecutionMetric {
  label: string;
  value: string | number;
  tone?: BadgeTone;
}

export type WorkflowOverallStatus = "queued" | "running" | "completed" | "partially_completed" | "failed";

export interface WorkflowExecutionViewProps {
  title: string;
  subtitle?: string;
  overallStatus: WorkflowOverallStatus;
  stages: WorkflowStage[];
  metrics: WorkflowExecutionMetric[];
  startedAt: string | null;
  finishedAt: string | null;
  /** Seconds elapsed so far - a real duration between two real timestamps,
   * computed by the caller (see this component's own docstring). */
  elapsedSeconds: number | null;
  /** Only ever rendered if provided - per Principle 4, this component
   * never fabricates an ETA when the caller has none to give it. */
  etaSeconds?: number | null;
  errorMessage?: string | null;
  /** A real, backend-derived sentence shown once the run reaches a
   * terminal state - never shown while still running/queued. */
  completionSummary?: string | null;
  /** Slot for a caller-specific action once terminal (e.g. "View
   * Prospects") - kept generic so this component never needs to know
   * what "results" means for a given domain. */
  resultsAction?: ReactNode;
}

const OVERALL_STATUS_STYLE: Record<WorkflowOverallStatus, { kind: StatusKind; label: string; tone: BadgeTone }> = {
  queued: { kind: "idle", label: "Queued", tone: "neutral" },
  running: { kind: "active", label: "Running", tone: "info" },
  completed: { kind: "success", label: "Completed", tone: "success" },
  partially_completed: { kind: "waiting", label: "Partially completed", tone: "warning" },
  failed: { kind: "failed", label: "Failed", tone: "danger" },
};

const STAGE_STATUS_KIND: Record<WorkflowStageStatus, StatusKind> = {
  completed: "success",
  running: "active",
  pending: "idle",
  failed: "failed",
};

function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}s`;
  const h = Math.floor(m / 60);
  const remM = m % 60;
  if (h === 0) return `${m}m ${s}s`;
  return `${h}h ${remM}m`;
}

export function WorkflowExecutionView({
  title,
  subtitle,
  overallStatus,
  stages,
  metrics,
  startedAt,
  finishedAt,
  elapsedSeconds,
  etaSeconds,
  errorMessage,
  completionSummary,
  resultsAction,
}: WorkflowExecutionViewProps) {
  const overall = OVERALL_STATUS_STYLE[overallStatus];
  const isTerminal = overallStatus === "completed" || overallStatus === "partially_completed" || overallStatus === "failed";

  return (
    <Card>
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
          {subtitle && <p className="mt-0.5 text-sm text-slate-400">{subtitle}</p>}
        </div>
        <StatusIndicator kind={overall.kind} label={overall.label} />
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-4 text-xs text-slate-500">
        <span>
          Started: {startedAt ? new Date(startedAt).toLocaleString() : "—"}
        </span>
        <span>
          Elapsed: {elapsedSeconds != null ? formatDuration(elapsedSeconds) : "—"}
        </span>
        {etaSeconds != null && <span>ETA: {formatDuration(etaSeconds)} remaining</span>}
        {finishedAt && <span>Finished: {new Date(finishedAt).toLocaleString()}</span>}
      </div>

      {metrics.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {metrics.map((m) => (
            <Badge key={m.label} tone={m.tone ?? "neutral"}>
              {m.label}: {m.value}
            </Badge>
          ))}
        </div>
      )}

      <div className="space-y-2 rounded-lg border border-border-hairline bg-surface-2 p-3">
        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">Stages</p>
        {stages.length === 0 && <p className="text-sm text-slate-500">No stages reported yet.</p>}
        {stages.map((stage) => (
          <div key={stage.key} className="flex items-center justify-between gap-3 text-sm">
            <StatusIndicator kind={STAGE_STATUS_KIND[stage.status]} label={stage.label} />
            {stage.detail && <span className="text-xs text-slate-500">{stage.detail}</span>}
          </div>
        ))}
      </div>

      {errorMessage && (
        <p className="mt-4 rounded-lg border border-status-danger/30 bg-status-danger/5 p-3 text-sm text-status-danger">
          {errorMessage}
        </p>
      )}

      {isTerminal && completionSummary && (
        <p className="mt-4 rounded-lg border border-border-hairline bg-surface-2 p-3 text-sm text-slate-200">
          {completionSummary}
        </p>
      )}

      {isTerminal && resultsAction && <div className="mt-4 flex justify-end">{resultsAction}</div>}
    </Card>
  );
}
