import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { Card } from "../design-system";
import { useAgentActivities } from "../ai-workforce/useAgentActivities";
import type { AgentActivityState } from "../ai-workforce/useAgentActivities";
import { describeAgentState } from "../ai-workforce/agentStateDisplay";

const SUMMARY_STATES: AgentActivityState[] = ["running", "waiting", "queued", "completed", "failed"];

/**
 * AI Workforce / AI Status — Middle Row, third column (M8.3 layout
 * revision). A compact, glanceable summary of the same real
 * AgentActivity data the full /ai-workforce page (M8.4) renders in
 * depth - this widget never re-implements that fetch/mapping logic, it
 * reuses useAgentActivities() and describeAgentState() as-is. "View full
 * roster" routes to the real page rather than duplicating its content
 * here in miniature.
 */
export function AiWorkforceStatusWidget() {
  const { activities, isLoading } = useAgentActivities();
  const navigate = useNavigate();

  const counts = SUMMARY_STATES.map((state) => ({
    state,
    label: state === "running" ? "Running" : describeAgentState(state, "", null).label,
    count: activities.filter((a) => a.state === state).length,
  }));

  return (
    <Card padding="compact" glow={counts[0].count > 0 ? "ai" : false} className="flex h-full flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-accent-ai-soft">AI Workforce</h3>
        <button
          onClick={() => navigate("/ai-workforce")}
          className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-300"
        >
          Full roster <ArrowRight className="h-3 w-3" aria-hidden="true" />
        </button>
      </div>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : activities.length === 0 ? (
        <p className="text-xs text-slate-500">No AI-driven workflows yet.</p>
      ) : (
        <div className="grid flex-1 grid-cols-5 gap-1.5">
          {counts.map((c) => (
            <div key={c.state} className="flex flex-col items-center justify-center rounded-lg bg-surface-2/60 py-2">
              <span className="text-base font-semibold text-slate-100">{c.count}</span>
              <span className="text-[10px] text-slate-500">{c.label}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
