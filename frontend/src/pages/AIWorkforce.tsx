import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card } from "../design-system";
import { useCompanies } from "../companies/CompanyContext";
import { useAgentActivities } from "../ai-workforce/useAgentActivities";
import { RosterSummary } from "../ai-workforce/RosterSummary";
import { AgentCard } from "../ai-workforce/AgentCard";
import { AgentTracePanel } from "../ai-workforce/AgentTracePanel";

/**
 * AIWorkforce — M8.4, real content behind "/ai-workforce" (previously
 * ComingSoon). Purpose-built page per Design Bible Section 9: "grid of
 * agent cards + per-agent execution trace - the visual home of the
 * Supervisor/Agent Runtime explainability data."
 *
 * Backed by the M8.4 backend addition (GET .../ai-workforce/activities,
 * .../activities/{id}/trace) - see app/ai_workforce/__init__.py's own
 * docstring for the storage/domain boundary this page's data ultimately
 * respects: this component only ever talks to the AgentActivity contract,
 * never anything shaped like "workflow instance."
 *
 * Known, disclosed gap (not fabricated around): "Thinking" (Supervisor-
 * level decide_next()) and "Reviewing" (human-approval waits) from the
 * Design Bible's illustrative vocabulary have no distinguishable backend
 * signal today - see agentStateDisplay.ts's own inline notes. Every
 * activity here renders as one of the 7 states the backend actually
 * reports, with a presentation-only verb substitution for "Running".
 */
export default function AIWorkforce() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const { activities, isLoading, error, refresh } = useAgentActivities();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!selectedId && activities.length > 0) setSelectedId(activities[0].id);
  }, [activities, selectedId]);

  const selected = activities.find((a) => a.id === selectedId) ?? null;

  if (!companiesLoading && !activeCompanyId) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="max-w-md text-center">
          <h1 className="text-lg font-semibold text-slate-100">Select a business</h1>
          <p className="mt-2 text-sm text-slate-400">
            The AI Workforce roster is scoped to one business at a time.
          </p>
          <button
            onClick={() => navigate("/businesses/new")}
            className="mt-4 rounded-lg bg-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-accent-primary/90"
          >
            Add your business
          </button>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">AI Workforce</h1>
          <p className="text-sm text-slate-500">Every AI-driven workflow currently tracked for this business.</p>
        </div>
        <button
          onClick={refresh}
          className="rounded-lg border border-border-hairline px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-border-hairline-strong hover:bg-surface-2"
        >
          Refresh
        </button>
      </div>

      {error && <p className="text-sm text-status-danger">{error}</p>}

      <RosterSummary activities={activities} />

      {isLoading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : activities.length === 0 ? (
        <Card className="text-center text-sm text-slate-500">
          No AI-driven workflows have run for this business yet.
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:col-span-2 xl:grid-cols-3">
            {activities.map((activity) => (
              <AgentCard
                key={activity.id}
                activity={activity}
                selected={activity.id === selectedId}
                onSelect={() => setSelectedId(activity.id)}
              />
            ))}
          </div>
          <div>{selected && <AgentTracePanel activity={selected} />}</div>
        </div>
      )}
    </div>
  );
}
