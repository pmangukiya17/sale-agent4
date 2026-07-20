import { Card } from "../design-system";
import { PlaceholderNotice } from "./PlaceholderNotice";

/**
 * Pipeline Overview funnel — Zone 3, Design Bible Section 8: "Discovered
 * → Researched → Outreach → Replied → Negotiation → Won, the top-of-
 * funnel conversion view, distinct from... the Sales Pipeline stage-box
 * widget in Zone 2."
 *
 * M8.7 Phase C finding: this widget previously rendered real-looking bars
 * from `countByLegacyStage(companies)` - the SAME disused `Company.stage`
 * model SalesPipelineWidget's own docstring already rejected as a data
 * source for the dashboard's flagship pipeline slot ("Company.stage is a
 * different, disused model... its own page, Pipeline.tsx, says outright
 * 'Discovery, scoring, and outreach are not wired up yet' - presenting it
 * in the dashboard's flagship Sales Pipeline slot implied a working
 * opportunity pipeline that doesn't exist, even with an honest caption
 * attached"). That exact reasoning applies here identically - a funnel
 * chart is a more polished visualization, but it's still legacy
 * `Company.stage` data standing in for a real Discovered→Researched→
 * Outreach→Replied→Negotiation→Won conversion funnel that doesn't exist
 * in the backend yet (no Opportunity/Deal model with a stage or
 * conversion-rate field - confirmed by reading every model in
 * app/models/). Restoring this widget to the Command Center (Section 8
 * requires it be present) without also fixing this would reintroduce the
 * exact honesty problem the CEO already corrected once for
 * SalesPipelineWidget. Fixed the same way, not left as a fabricated
 * chart: an honest "not yet implemented" placeholder, distinctly labeled
 * from Sales Pipeline so the two slots are never confused for each other.
 */
export function PipelineFunnel() {
  return (
    <Card padding="compact" className="flex h-full flex-col gap-2">
      <h3 className="text-xs font-semibold text-slate-100">Pipeline Overview</h3>
      <PlaceholderNotice
        kind="not-implemented"
        reason="No Discovered→Researched→Outreach→Replied→Negotiation→Won conversion funnel exists in the backend yet."
      />
    </Card>
  );
}
