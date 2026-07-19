import { Card } from "../design-system";
import type { AgentActivity, AgentActivityState } from "./useAgentActivities";
import { describeAgentState } from "./agentStateDisplay";

const SUMMARY_STATES: AgentActivityState[] = ["running", "waiting", "queued", "completed", "failed"];

/**
 * Small roster-wide summary strip - real counts by AgentActivityState,
 * reusing describeAgentState purely for its label (a running count is
 * always labeled "Running", never split per-agent-verb at the aggregate
 * level - the verb distinction only makes sense per card).
 */
export function RosterSummary({ activities }: { activities: AgentActivity[] }) {
  const counts = SUMMARY_STATES.map((state) => ({
    state,
    label: state === "running" ? "Running" : describeAgentState(state, "", null).label,
    count: activities.filter((a) => a.state === state).length,
  }));

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {counts.map((c) => (
        <Card key={c.state} className="flex flex-col items-center gap-1 py-3">
          <span className="text-xl font-semibold text-slate-100">{c.count}</span>
          <span className="text-xs text-slate-500">{c.label}</span>
        </Card>
      ))}
    </div>
  );
}
