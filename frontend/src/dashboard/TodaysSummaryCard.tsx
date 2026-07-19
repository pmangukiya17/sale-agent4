import type { DashboardProspect } from "./useDashboardPortfolio";
import { todaysSummary } from "./selectors";

/**
 * Today's Summary — Zone 1 companion (Design Bible Section 8: today's
 * discrete counts, NOT a duplicate KPI row). Derived entirely from real
 * Prospect timestamps already fetched for the KPI strip/World Map -
 * discovered/reviewed/seen "today" by UTC calendar date (see
 * selectors.ts's isToday).
 *
 * Rendered as a slim single-line strip, not a full Card - part of the
 * single-screen/no-vertical-scroll polish pass: this used to be its own
 * padded Card stacked below the KPI grid, which cost ~90px of vertical
 * budget for three numbers. Same real data, same position (directly
 * under Zone 1), just without the extra card chrome.
 */
export function TodaysSummaryCard({ prospects, isLoading }: { prospects: DashboardProspect[]; isLoading: boolean }) {
  const summary = todaysSummary(prospects);

  if (isLoading) {
    return <p className="text-xs text-slate-600">Loading today's summary…</p>;
  }

  return (
    <div className="flex items-center gap-5 text-xs text-slate-500">
      <span className="font-medium text-slate-400">Today</span>
      <span>
        <span className="font-semibold text-slate-200">{summary.discoveredToday}</span> discovered
      </span>
      <span>
        <span className="font-semibold text-slate-200">{summary.reviewedToday}</span> reviewed
      </span>
      <span>
        <span className="font-semibold text-slate-200">{summary.seenToday}</span> updated
      </span>
    </div>
  );
}
