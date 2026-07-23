import { Card } from "../design-system";
import type { DashboardProspect } from "./useDashboardPortfolio";
import { PROSPECT_STATUS_LABELS, PROSPECT_STATUS_ORDER, countByStatus } from "./selectors";

/**
 * AI Pipeline widget — Bottom Row, purple (accent-ai), Design Bible
 * Section 8. Real data: the count of Prospects (the actual M1-M7 entity)
 * at each ProspectStatus value. The Design Bible's illustrative stage
 * list (Discovery→Research→Qualification→Personalization→Outreach→Reply
 * Intelligence) describes which AI ENGINE touched a prospect, but no
 * single backend field records "which engine last ran" - ProspectStatus
 * (new/scored/qualified/approved/...) is the one real field that tracks
 * where a prospect actually is, so that's the vocabulary shown here,
 * labeled honestly rather than relabeled to match the concept art exactly.
 *
 * Kept as a distinct widget/color from SalesPipelineWidget per the
 * explicit "two different jobs, both kept" call in the Design Bible - this
 * one is AI-engine status, that one is the CRM deal-stage funnel.
 *
 * Rendered compact (M8.3 single-screen revision): only the top 4 stages
 * by count are shown, capped height, tight spacing - a single-screen
 * operational card, not a full breakdown (that fuller view still exists
 * on the Prospects/Pipeline pages this feeds from).
 *
 * Track B1 UI refinement: migrated from `glow={... ? "ai" : false}` to
 * `accent="purple"` (ambient, always on) + `active={prospects.length > 0}`
 * (same condition as before, now the breathing layer). Purple is a
 * deliberately DIFFERENT rgb from AI Workforce's violet, per the CEO's
 * explicit palette - the two AI cards now have distinct, not identical,
 * identity colors, even though both are still "AI-attributed." Scope
 * note: only the Card-level glow changed here - the title text
 * (`text-accent-ai-soft`) and progress-bar fill (`bg-accent-ai`) below
 * are untouched, still the original ai/violet tokens, since recoloring
 * those wasn't part of the requested change (glow only, no functional/
 * broader visual changes).
 */
export function AiPipelineWidget({ prospects, isLoading }: { prospects: DashboardProspect[]; isLoading: boolean }) {
  const counts = countByStatus(prospects);
  const total = prospects.length || 1;
  const topStages = PROSPECT_STATUS_ORDER.filter((s) => counts[s]).slice(0, 4);

  return (
    <Card
      padding="compact"
      accent="purple"
      active={prospects.length > 0}
      className="flex h-full flex-col gap-2"
      // TEMPORARY DEBUG OVERRIDE - not a production value. Card merges
      // `{...ambientGlowStyle(accent), ...style}`, so this `style` prop
      // wins and replaces the normal ambient box-shadow outright on this
      // one card only. Deliberately extreme (60px blur, +8px POSITIVE
      // spread so the shadow rect can't be swallowed behind the card's
      // own opaque background the way a negative spread can, 85% alpha)
      // purely to give an unmistakable yes/no signal on whether the
      // rendering path (DOM/CSS/build) works at all, before touching any
      // other card's real values. Revert once confirmed.
      style={{ boxShadow: "0 0 60px 8px rgba(168,85,247,0.85)" }}
    >
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-accent-ai-soft">AI Pipeline</h3>
        <span className="text-[11px] text-slate-500">{prospects.length}</span>
      </div>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : prospects.length === 0 ? (
        <p className="text-xs text-slate-500">No prospects yet.</p>
      ) : (
        <div className="space-y-1.5">
          {topStages.map((s) => (
            <div key={s} className="flex items-center gap-1.5">
              <span className="w-16 shrink-0 truncate text-[11px] text-slate-400">{PROSPECT_STATUS_LABELS[s]}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-pill bg-surface-2">
                <div className="h-full rounded-pill bg-accent-ai" style={{ width: `${((counts[s] ?? 0) / total) * 100}%` }} />
              </div>
              <span className="w-4 shrink-0 text-right text-[11px] text-slate-500">{counts[s]}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
