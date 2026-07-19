import { useNavigate } from "react-router-dom";
import { Card, Badge } from "../design-system";
import type { DashboardProspect } from "./useDashboardPortfolio";
import { needsReviewList } from "./selectors";
import { useCompanies } from "../companies/CompanyContext";

/**
 * Today's Priorities — Bottom Row. Real: the highest-scored prospects
 * currently sitting in "scored"/"in_review" status (selectors.ts's
 * needsReviewList) - these are the ones actually waiting on a human
 * decision right now, which is what "priority" means with the data that
 * exists. Clicking a row routes to the real Prospects page (scoped to the
 * active business) rather than a page that doesn't exist yet.
 *
 * `limit`/`compact` (M8.3 single-screen revision): the bottom operational
 * row is 7 glanceable cards on one screen, not one full-height card - a
 * smaller `limit` and tighter `compact` typography let this same
 * component serve both a full card (elsewhere) and this dense role
 * without a second implementation.
 */
export function TodaysPriorities({
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
  const navigate = useNavigate();
  const { activeCompanyId } = useCompanies();
  const priorities = needsReviewList(prospects, limit);

  return (
    <Card padding={compact ? "compact" : "normal"} className="flex h-full flex-col gap-2">
      <h3 className={compact ? "text-xs font-semibold text-slate-100" : "text-sm font-semibold text-slate-100"}>
        Today's Priorities
      </h3>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : priorities.length === 0 ? (
        <p className="text-xs text-slate-500">Nothing waiting on review.</p>
      ) : (
        <ul className={compact ? "space-y-1" : "space-y-2"}>
          {priorities.map((p) => (
            <li key={p.id}>
              <button
                onClick={() => activeCompanyId && navigate(`/businesses/${activeCompanyId}/discovery/prospects`)}
                className={compact ? "flex w-full items-center justify-between rounded px-1.5 py-1 text-left hover:bg-surface-2" : "flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left hover:bg-surface-2"}
              >
                <span className={compact ? "truncate text-xs text-slate-200" : "truncate text-sm text-slate-200"}>{p.name}</span>
                <span className="flex shrink-0 items-center gap-1.5">
                  {p.total_score !== null && <span className="text-[11px] text-slate-500">{p.total_score.toFixed(0)}</span>}
                  {!compact && <Badge tone="warning">Needs review</Badge>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
