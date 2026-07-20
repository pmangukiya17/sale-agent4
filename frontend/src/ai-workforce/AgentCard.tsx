import { Card, StatusIndicator, cn } from "../design-system";
import type { AgentActivity } from "./useAgentActivities";
import { describeAgentState } from "./agentStateDisplay";

/**
 * AgentCard — one roster entry (Design Bible Section 9: "grid of agent
 * cards"). Glows purple only while genuinely active (`state === "running"`
 * or `"waiting"`) - terminal states never glow, matching Card.tsx's own
 * "glow means live or currently AI-touched right now" rule.
 */
export function AgentCard({
  activity,
  selected,
  onSelect,
}: {
  activity: AgentActivity;
  selected: boolean;
  onSelect: () => void;
}) {
  const display = describeAgentState(activity.state, activity.workflow_key, activity.current_action_key);
  const isLive = activity.state === "running" || activity.state === "waiting";

  return (
    <button onClick={onSelect} className="text-left">
      <Card
        glow={isLive ? "ai" : false}
        className={cn("flex flex-col gap-3 transition-colors", selected && "border-accent-ai/60")}
      >
        <div className="flex items-center justify-between">
          <h3 className="truncate text-sm font-semibold text-slate-100">{activity.workflow_key}</h3>
          <StatusIndicator kind={display.statusKind} label={display.label} />
        </div>
        <dl className="grid grid-cols-2 gap-2 text-xs text-slate-500">
          <div>
            <dt className="text-[10px] uppercase tracking-wide">Step</dt>
            <dd className="truncate text-slate-300">{activity.current_step_id}</dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wide">Action</dt>
            <dd className="truncate text-slate-300">{activity.current_action_key ?? "—"}</dd>
          </div>
        </dl>
        <p className="text-[11px] text-slate-500">
          Updated {new Date(activity.updated_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
        </p>
      </Card>
    </button>
  );
}
