import { Card, PlaceholderNotice } from "../design-system";
import { useOpportunityFunnel } from "./useOpportunityFunnel";

/**
 * Pipeline Overview funnel — Zone 3, Design Bible Section 8. Track C4
 * (dashboard-capabilities-architecture-plan.md, Section 3): wired to the
 * real Opportunity domain - the same GET .../opportunities/funnel
 * response Sales Pipeline reads (see useOpportunityFunnel.ts's own
 * docstring), but this widget also renders `conversion_rate_from_previous`
 * - the one field Sales Pipeline's compact stage-box view doesn't need,
 * per the architecture doc's own Section 3.4 "one endpoint, two frontend
 * granularities" call.
 *
 * Renders the sequential chain (Qualified Lead → Meeting → Sample →
 * Quotation → Negotiation → Purchase Order → Won) with each stage's
 * conversion percentage FROM the previous stage - see
 * app.opportunities.service.compute_funnel's own docstring for exactly
 * what this percentage does and does not mean (a current-distribution
 * ratio, not a historical cohort conversion rate - stages may be
 * skipped, per Track C3's own design decision, so this is an honest
 * approximation, not a claim about "what fraction of deals that ever
 * reached stage N reached stage N+1"). Lost is shown as a separate
 * drop-off line beneath the chain, not a seventh sequential box - it's a
 * terminal OUTCOME, not a stage every deal passes through on its way
 * somewhere else.
 *
 * Track B1 UI refinement (superseded by this track for `active`, kept
 * for `accent`): `accent="teal"` ambient identity glow. `active` now
 * fires on real Opportunity activity, the same "never fabricate
 * liveliness" rule already applied elsewhere on this dashboard.
 */
const FUNNEL_SEQUENCE = [
  "qualified_lead",
  "meeting",
  "sample",
  "quotation",
  "negotiation",
  "purchase_order",
  "closed_won",
] as const;

const STAGE_LABELS: Record<string, string> = {
  qualified_lead: "Qualified Lead",
  meeting: "Meeting",
  sample: "Sample",
  quotation: "Quotation",
  negotiation: "Negotiation",
  purchase_order: "Purchase Order",
  closed_won: "Won",
};

export function PipelineFunnel() {
  const { funnel, isLoading, error } = useOpportunityFunnel();
  const byStage = Object.fromEntries(funnel.map((row) => [row.stage, row]));
  const lostCount = byStage["closed_lost"]?.count ?? 0;
  const totalCount = funnel.reduce((sum, row) => sum + row.count, 0);

  return (
    <Card
      padding="compact"
      accent="teal"
      active={!isLoading && !error && totalCount > 0}
      className="flex h-full flex-col gap-2"
    >
      <h3 className="text-xs font-semibold text-slate-100">Pipeline Overview</h3>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : error ? (
        <PlaceholderNotice kind="no-data" reason={error} />
      ) : totalCount === 0 ? (
        <PlaceholderNotice kind="no-data" reason="No opportunities yet - the conversion funnel is real, there's just nothing here." />
      ) : (
        <>
          <ul className="space-y-1">
            {FUNNEL_SEQUENCE.map((stage) => {
              const row = byStage[stage];
              const conversion = row?.conversion_rate_from_previous ?? null;
              return (
                <li key={stage} className="flex items-center justify-between rounded px-1.5 py-1 bg-surface-2/50">
                  <span className="truncate text-xs text-slate-300">{STAGE_LABELS[stage]}</span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    {conversion !== null && <span className="text-[10px] text-slate-500">{conversion}%</span>}
                    <span className="text-xs font-semibold text-slate-100">{row?.count ?? 0}</span>
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="mt-auto text-[11px] text-slate-500">{lostCount} Lost along the way</p>
        </>
      )}
    </Card>
  );
}
