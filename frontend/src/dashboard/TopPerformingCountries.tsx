import { Card } from "../design-system";
import type { DashboardProspect } from "./useDashboardPortfolio";
import { topPerformingCountries } from "./selectors";

/**
 * Top Performing Countries — Bottom Row ranked list. Real: countries
 * ranked by average Prospect.total_score (selectors.ts's
 * topPerformingCountries), using the same already-fetched prospect list
 * as the World Map and KPI strip. Requires at least one scored prospect
 * per country to appear - unscored-only countries are correctly excluded
 * rather than shown with a fabricated "0" average.
 *
 * `limit`/`compact` - see TodaysPriorities.tsx's docstring for why these
 * exist (single-screen operational row, M8.3 revision).
 *
 * Track B1 UI refinement: `accent="emerald"` ambient identity glow only -
 * no `active` state. This is a ranked snapshot (like ActivityTimeline),
 * not a single "country X currently has activity" event the way
 * CountryIntelligencePanel's own emerald identity is - that panel's
 * `active` condition is about ONE selected country, this card ranks
 * several at once, so there's no equally clean single boolean signal to
 * drive a breathing layer from without it applying to the whole list
 * indiscriminately.
 */
export function TopPerformingCountries({
  prospects,
  isLoading,
  limit = 5,
  compact = false,
}: {
  prospects: DashboardProspect[];
  isLoading: boolean;
  limit?: number;
  compact?: boolean;
}) {
  const ranked = topPerformingCountries(prospects, limit);

  return (
    <Card padding={compact ? "compact" : "normal"} accent="emerald" className="flex h-full flex-col gap-2">
      <h3 className={compact ? "text-xs font-semibold text-slate-100" : "text-sm font-semibold text-slate-100"}>
        Top Countries
      </h3>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : ranked.length === 0 ? (
        <p className="text-xs text-slate-500">No scored prospects yet.</p>
      ) : (
        <ol className={compact ? "space-y-1" : "space-y-2"}>
          {ranked.map((c, i) => (
            <li key={c.country} className="flex items-center justify-between text-xs">
              <span className="flex min-w-0 items-center gap-1.5 text-slate-300">
                <span className="text-slate-500">{i + 1}</span>
                <span className="truncate">{c.country}</span>
              </span>
              <span className="shrink-0 font-medium text-slate-300">{c.avgScore?.toFixed(0)}</span>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
