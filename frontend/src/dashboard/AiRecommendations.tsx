import { Card, PlaceholderNotice } from "../design-system";

/**
 * AI Recommendations — Zone 3. The Recommendation model and its API are
 * real (backend/app/api/routes/recommendations.py), but the endpoint is
 * scoped to a single prospect only:
 *   GET /company-profiles/{id}/prospects/{prospect_id}/recommendations
 * There is no cross-portfolio "all recommendations for this business"
 * endpoint. Building an aggregate view here would mean fetching the full
 * prospect list and firing one recommendations request per prospect (an
 * N+1 fan-out) - a performance anti-pattern no other page in this codebase
 * does, and not something to quietly introduce into a "production
 * quality" dashboard. Until a real aggregate endpoint exists, this is an
 * honest placeholder rather than either a fabricated list or a silent N+1.
 *
 * Track B1 UI refinement: `accent="cyan"` ambient identity glow only - no
 * `active` state, same "don't imply live activity on an honest
 * placeholder" reasoning as SalesPipelineWidget/PipelineFunnel.
 */
export function AiRecommendations() {
  return (
    <Card padding="compact" accent="cyan" className="flex h-full flex-col gap-2">
      <h3 className="text-xs font-semibold text-slate-100">AI Recommendations</h3>
      <PlaceholderNotice kind="not-implemented" reason="No cross-portfolio recommendations endpoint exists yet." />
    </Card>
  );
}
