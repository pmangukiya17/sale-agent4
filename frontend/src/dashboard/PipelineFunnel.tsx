import { Card } from "../design-system";
import type { LegacyCompany } from "./useDashboardPortfolio";
import { FUNNEL_GROUPS, countByLegacyStage } from "./selectors";

/**
 * Pipeline Overview funnel — Zone 3 (Design Bible: Discovered → Researched
 * → Outreach → Replied → Negotiation → Won, "distinct from the Zone 2
 * stage-box widget"). Same real Company.stage data as SalesPipelineWidget,
 * but collapsed into 6 macro groups (selectors.ts's FUNNEL_GROUPS) instead
 * of shown as all 18 raw enum values - a genuinely different aggregation
 * and visualization (a funnel, not a stage list), satisfying the
 * "distinct from Zone 2" requirement without a second data source.
 */
export function PipelineFunnel({ companies, isLoading }: { companies: LegacyCompany[]; isLoading: boolean }) {
  const counts = countByLegacyStage(companies);
  const groupCounts = FUNNEL_GROUPS.map((g) => ({
    label: g.label,
    count: g.stages.reduce((sum, s) => sum + (counts[s] ?? 0), 0),
  }));
  const max = Math.max(1, ...groupCounts.map((g) => g.count));

  return (
    <Card className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-slate-100">Pipeline Overview</h3>
      {isLoading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : companies.length === 0 ? (
        <p className="text-sm text-slate-500">No companies in the CRM list yet.</p>
      ) : (
        <div className="flex items-end gap-2">
          {groupCounts.map((g) => (
            <div key={g.label} className="flex flex-1 flex-col items-center gap-1.5">
              <div className="flex h-24 w-full items-end">
                <div
                  className="w-full rounded-t bg-accent-primary/70"
                  style={{ height: `${(g.count / max) * 100}%` }}
                />
              </div>
              <span className="text-xs font-medium text-slate-300">{g.count}</span>
              <span className="text-center text-[10px] leading-tight text-slate-500">{g.label}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
