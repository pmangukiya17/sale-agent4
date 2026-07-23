import { Card, PlaceholderNotice } from "../design-system";
import { useOpportunityFunnel } from "./useOpportunityFunnel";

/**
 * Sales Pipeline widget — Zone 2, blue (accent-primary), Design Bible
 * Section 8. Track C4 (dashboard-capabilities-architecture-plan.md,
 * Section 2): wired to the real Opportunity domain Track C3 built - a
 * compact stage-box view of the current deal-stage distribution
 * (Qualified Lead → Meeting → Sample → Quotation → Negotiation →
 * Purchase Order), reading the same GET .../opportunities/funnel
 * endpoint Pipeline Overview uses (see useOpportunityFunnel.ts's own
 * docstring for why one endpoint serves both). This widget only needs
 * stage-box counts, not the conversion-rate math Pipeline Overview also
 * reads from the same response - a frontend-shape decision the
 * architecture doc's own Section 2.4 left open, resolved here by simply
 * not rendering that field, not by requesting a lighter endpoint.
 *
 * Won/Lost are shown as a small footer summary rather than two more
 * stage boxes - they're terminal OUTCOMES a deal exits the sequential
 * pipeline into, not another step in the "where is this deal right now"
 * box row (same reasoning compute_funnel's own docstring gives for why
 * CLOSED_LOST sits outside `_FUNNEL_SEQUENCE`).
 *
 * Track B1 UI refinement (superseded by this track for the `active`
 * state, kept for the `accent`): `accent="blue"` ambient identity glow.
 * `active` now fires on real Opportunity activity (at least one
 * Opportunity exists) - the same "never fabricate liveliness" rule
 * Track C1/C2 already applied to Open Conversations/AI Recommendations.
 */
const OPEN_STAGE_ORDER = [
  "qualified_lead",
  "meeting",
  "sample",
  "quotation",
  "negotiation",
  "purchase_order",
] as const;

const STAGE_LABELS: Record<string, string> = {
  qualified_lead: "Qualified Lead",
  meeting: "Meeting",
  sample: "Sample",
  quotation: "Quotation",
  negotiation: "Negotiation",
  purchase_order: "Purchase Order",
};

export function SalesPipelineWidget() {
  const { funnel, isLoading, error } = useOpportunityFunnel();
  const byStage = Object.fromEntries(funnel.map((row) => [row.stage, row]));
  const wonCount = byStage["closed_won"]?.count ?? 0;
  const lostCount = byStage["closed_lost"]?.count ?? 0;
  const openTotal = OPEN_STAGE_ORDER.reduce((sum, stage) => sum + (byStage[stage]?.count ?? 0), 0);
  const hasAnyOpportunity = openTotal + wonCount + lostCount > 0;

  return (
    <Card
      padding="compact"
      accent="blue"
      active={!isLoading && !error && hasAnyOpportunity}
      className="flex h-full flex-col gap-2"
    >
      <h3 className="text-xs font-semibold text-accent-primary">Sales Pipeline</h3>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : error ? (
        <PlaceholderNotice kind="no-data" reason={error} />
      ) : !hasAnyOpportunity ? (
        <PlaceholderNotice kind="no-data" reason="No opportunities yet - the Opportunity domain is real, there's just nothing here." />
      ) : (
        <>
          <ul className="space-y-1">
            {OPEN_STAGE_ORDER.map((stage) => (
              <li key={stage} className="flex items-center justify-between rounded px-1.5 py-1 bg-surface-2/50">
                <span className="truncate text-xs text-slate-300">{STAGE_LABELS[stage]}</span>
                <span className="text-xs font-semibold text-slate-100">{byStage[stage]?.count ?? 0}</span>
              </li>
            ))}
          </ul>
          <div className="mt-auto flex items-center justify-between text-[11px] text-slate-500">
            <span>{wonCount} Won</span>
            <span>{lostCount} Lost</span>
          </div>
        </>
      )}
    </Card>
  );
}
