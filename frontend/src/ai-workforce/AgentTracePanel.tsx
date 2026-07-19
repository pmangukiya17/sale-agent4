import { Card, Badge, type BadgeTone } from "../design-system";
import type { AgentActivity } from "./useAgentActivities";
import { useActivityTrace, type AgentActivityTraceStatus } from "./useActivityTrace";

const TRACE_STATUS_TONE: Record<AgentActivityTraceStatus, BadgeTone> = {
  pending: "neutral",
  running: "info",
  succeeded: "success",
  failed: "danger",
  skipped: "neutral",
};

/**
 * AgentTracePanel — the per-agent execution trace (Design Bible Section
 * 9: "the visual home of the Supervisor/Agent Runtime explainability
 * data"). Real, ordered attempt history from GET .../activities/{id}/trace
 * - one row per WorkflowStepInvocation, oldest first, including retries
 * (a retried step is a new row with an incremented attempt_number, never
 * an edit to the old one - shown here exactly that way, nothing collapsed
 * or hidden).
 */
export function AgentTracePanel({ activity }: { activity: AgentActivity }) {
  const { entries, isLoading, error } = useActivityTrace(activity.company_profile_id, activity.id);

  return (
    <Card className="flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold text-slate-100">{activity.workflow_key}</h3>
        <p className="text-xs text-slate-500">Execution trace</p>
      </div>
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {error && <p className="text-sm text-status-danger">{error}</p>}
      {!isLoading && !error && entries.length === 0 && (
        <p className="text-sm text-slate-500">No step attempts recorded yet - this activity is still queued.</p>
      )}
      {entries.length > 0 && (
        <ol className="max-h-96 space-y-2 overflow-y-auto pr-1">
          {entries.map((entry) => (
            <li key={entry.id} className="flex items-start justify-between gap-2 rounded-lg border border-border-hairline bg-surface-2/40 p-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm text-slate-200">{entry.step_id}</p>
                <p className="truncate text-xs text-slate-500">
                  {entry.action_key}
                  {entry.attempt_number > 1 && ` · attempt ${entry.attempt_number}`}
                </p>
                {entry.error && <p className="mt-1 truncate text-xs text-status-danger">{entry.error}</p>}
              </div>
              <Badge tone={TRACE_STATUS_TONE[entry.status]}>{entry.status}</Badge>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
