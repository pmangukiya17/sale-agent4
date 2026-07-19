import { Card, Badge } from "../design-system";
import type { DashboardProspect } from "./useDashboardPortfolio";
import { recentActivity } from "./selectors";

/**
 * Activity Timeline — reusable feed component (Design Bible: "reusable
 * anywhere workflow history is displayed"). On this dashboard it's built
 * from real Prospect timestamps (first_discovered_at/reviewed_at) across
 * the whole portfolio - not the more granular, real per-event
 * ProspectTimelineEvent model (prospect_timeline.py), because that
 * endpoint is scoped to one prospect at a time
 * (GET .../prospects/{id}/timeline) with no cross-portfolio equivalent.
 *
 * `limit`/`compact` - see TodaysPriorities.tsx's docstring for why these
 * exist (single-screen operational row, M8.3 revision). `compact` also
 * drops the internal max-h scroll area in favor of a fixed, non-scrolling
 * short list, since a scrollbar inside a small bottom-row card reads as
 * clutter at that size - the fuller, scrollable variant stays available
 * for non-compact use (e.g. a future Prospect detail page).
 */
export function ActivityTimeline({
  prospects,
  isLoading,
  limit = 8,
  compact = false,
}: {
  prospects: DashboardProspect[];
  isLoading: boolean;
  limit?: number;
  compact?: boolean;
}) {
  const items = recentActivity(prospects, limit);

  return (
    <Card padding={compact ? "compact" : "normal"} className="flex h-full flex-col gap-2">
      <h3 className={compact ? "text-xs font-semibold text-slate-100" : "text-sm font-semibold text-slate-100"}>Activity</h3>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-xs text-slate-500">No recent activity yet.</p>
      ) : (
        <ul className={compact ? "space-y-1" : "max-h-64 space-y-2 overflow-y-auto pr-1"}>
          {items.map((item) => (
            <li key={item.id} className="flex items-start justify-between gap-2 text-xs">
              <div className="min-w-0">
                <p className="truncate text-slate-200">{item.name}</p>
                {!compact && (
                  <p className="text-slate-500">
                    {item.kind === "discovered" ? "Discovered" : "Reviewed"}
                    {item.country ? ` · ${item.country}` : ""}
                  </p>
                )}
              </div>
              {compact ? (
                <span className="shrink-0 text-slate-500">
                  {new Date(item.at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </span>
              ) : (
                <Badge tone={item.kind === "reviewed" ? "success" : "neutral"}>
                  {new Date(item.at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </Badge>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
