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
 *
 * M8.7 Phase F: the list carries `aria-live="polite"` - Section 12's
 * requirement that the Activity Timeline is a real live region, not just
 * a visual feed - so a screen-reader user is told when new activity
 * appears after a portfolio refresh, the same way a sighted user notices
 * a new row. No CSS insert-animation exists on this list today (each
 * refresh re-renders the whole list from `prospects`, it doesn't
 * literally insert one new DOM row with a transition), so there is no
 * category-1 motion here yet needing a `prefers-reduced-motion` variant -
 * only the aria-live wiring applies for now.
 *
 * Track B1 UI refinement: `accent="slate"` ambient identity glow only -
 * no `active` state. Unlike TodaysPriorities/AiPipelineWidget, this card
 * shows a historical feed, not a "something is happening right now"
 * event - "there is recent activity" isn't meaningfully different from
 * "there is data," so it doesn't get the breathing layer, same judgment
 * already applied to the KPI strip's static count cards.
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
    <Card padding={compact ? "compact" : "normal"} accent="slate" className="flex h-full flex-col gap-2">
      <h3 className={compact ? "text-xs font-semibold text-slate-100" : "text-sm font-semibold text-slate-100"}>Activity</h3>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-xs text-slate-500">No recent activity yet.</p>
      ) : (
        <ul className={compact ? "space-y-1" : "max-h-64 space-y-2 overflow-y-auto pr-1"} aria-live="polite">
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
