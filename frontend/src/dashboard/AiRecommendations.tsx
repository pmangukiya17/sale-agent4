import { useNavigate } from "react-router-dom";
import { Card, PlaceholderNotice, Badge } from "../design-system";
import { useCompanies } from "../companies/CompanyContext";
import { useRecommendationsPortfolio } from "./useRecommendationsPortfolio";

/**
 * AI Recommendations — Zone 3/bottom row. Track C2
 * (dashboard-capabilities-architecture-plan.md): the Recommendation
 * model and its per-prospect API were already real
 * (backend/app/api/routes/recommendations.py); the only genuine gap was
 * a cross-portfolio "all recommendations for this business" endpoint,
 * which C2 added rather than fetching the full prospect list and firing
 * one recommendations request per prospect (the N+1 fan-out this
 * component's previous placeholder docstring explicitly refused to do).
 * See useRecommendationsPortfolio.ts for the endpoint this now calls.
 *
 * `limit`/`compact` (mirrors TodaysPriorities.tsx's own convention): the
 * bottom operational row is 8 glanceable cards on one screen, not one
 * full-height card.
 *
 * Track C2 glow update: `accent="cyan"` stays the card's ambient
 * identity color; `active` now fires on `recommendations.length > 0` -
 * a real signal, the same "never fabricate liveliness" rule Track C1
 * applied to Open Conversations.
 */
export function AiRecommendations({ limit = 5, compact = false }: { limit?: number; compact?: boolean } = {}) {
  const navigate = useNavigate();
  const { activeCompanyId } = useCompanies();
  const { recommendations, isLoading, error } = useRecommendationsPortfolio(limit);

  return (
    <Card
      padding={compact ? "compact" : "normal"}
      accent="cyan"
      active={!isLoading && !error && recommendations.length > 0}
      className="flex h-full flex-col gap-2"
    >
      <h3 className={compact ? "text-xs font-semibold text-slate-100" : "text-sm font-semibold text-slate-100"}>
        AI Recommendations
      </h3>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : error ? (
        <PlaceholderNotice kind="no-data" reason={error} />
      ) : recommendations.length === 0 ? (
        <PlaceholderNotice kind="no-data" reason="No recommendations yet - the AI Analysis Engine hasn't generated any for this business." />
      ) : (
        <ul className={compact ? "space-y-1" : "space-y-2"}>
          {recommendations.map((rec) => (
            <li key={rec.id}>
              <button
                onClick={() => activeCompanyId && navigate(`/businesses/${activeCompanyId}/discovery/prospects`)}
                className={
                  compact
                    ? "flex w-full items-center justify-between rounded px-1.5 py-1 text-left hover:bg-surface-2"
                    : "flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left hover:bg-surface-2"
                }
              >
                <span className="min-w-0 flex-1 truncate">
                  <span className={compact ? "block truncate text-xs text-slate-200" : "block truncate text-sm text-slate-200"}>
                    {rec.title}
                  </span>
                  <span className="block truncate text-[11px] text-slate-500">{rec.prospect.name}</span>
                </span>
                <span className="flex shrink-0 items-center gap-1.5">
                  {rec.confidence !== null && <span className="text-[11px] text-slate-500">{Math.round(rec.confidence)}%</span>}
                  {!compact && <Badge tone="info">{rec.recommendation_type.replace(/_/g, " ")}</Badge>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
