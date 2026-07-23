import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card } from "../design-system";
import { useCompanies } from "../companies/CompanyContext";
import { useDashboardPortfolio } from "../dashboard/useDashboardPortfolio";
import { useCountryReference } from "../dashboard/useCountryReference";
import { useWorldGeometry } from "../dashboard/useWorldGeometry";
import { aggregateByCountry } from "../dashboard/selectors";
import { KpiStrip } from "../dashboard/KpiStrip";
import { TodaysSummaryCard } from "../dashboard/TodaysSummaryCard";
import { WorldMap, type WorldMapCountry } from "../dashboard/WorldMap";
import { CountryIntelligencePanel } from "../dashboard/CountryIntelligencePanel";
import { AiWorkforceStatusWidget } from "../dashboard/AiWorkforceStatusWidget";
import { AiPipelineWidget } from "../dashboard/AiPipelineWidget";
import { SalesPipelineWidget } from "../dashboard/SalesPipelineWidget";
import { PipelineFunnel } from "../dashboard/PipelineFunnel";
import { TodaysPriorities } from "../dashboard/TodaysPriorities";
import { AiRecommendations } from "../dashboard/AiRecommendations";
import { MailboxBrief } from "../dashboard/MailboxBrief";
import { TopPerformingCountries } from "../dashboard/TopPerformingCountries";
import { ActivityTimeline } from "../dashboard/ActivityTimeline";

/**
 * CommandCenter — M8.3, real content behind "/command-center" and the "/"
 * redirect target.
 *
 * LAYOUT (second single-screen revision, after real-browser feedback that
 * the first pass still let the map force a scroll): three fixed-role rows
 * instead of "map fills whatever's left."
 *   - Top row (`shrink-0`): KPI strip + Today's Summary - intrinsic height.
 *   - Middle row (`flex-1 min-h-0 max-h-[46vh]`): World Map | Country
 *     Intelligence | AI Workforce status, three columns, map weighted
 *     ~50% width. The `max-h-[46vh]` cap is the actual fix for "map takes
 *     too much vertical space" - the map is `flex-1` so it uses available
 *     room, but can never grow past ~46% of the viewport regardless of
 *     screen height. Country Intelligence is back to being a permanent
 *     column (not the slide-over drawer the previous pass used) per this
 *     revision's explicit 3-column middle-row structure - it defaults to
 *     the top-scoring country so the column is never empty, and still
 *     updates on map click.
 *   - Bottom row (`flex-1 min-h-0`): eight compact cards in one dense
 *     grid (AI Pipeline, Sales Pipeline, Pipeline Overview funnel,
 *     Priorities, Recommendations, Mailbox Brief, Activity, Top
 *     Countries) - all visible simultaneously, not behind tabs. Pipeline
 *     Overview restored here in M8.7 Phase C (Design Bible Section 8
 *     requires it; it had been dropped from composition, not deleted,
 *     during the M8.3 layout revision) - see PipelineFunnel.tsx's own
 *     docstring for why it was also rewritten to an honest placeholder
 *     rather than simply restored as-is. Because the middle row's height
 *     is capped, this row reliably gets the space it needs instead of
 *     being squeezed off-screen.
 * Every widget here uses Card's new `padding="compact"` variant (see
 * Card.tsx) and, where applicable, a `limit`/`compact` prop to show fewer
 * rows - same components, same data, denser presentation only.
 *
 * Glass/glow: glass stays restrained to Design Bible Section 4.5's rule
 * (overlays only - command palette, modals; NOT standing dashboard
 * cards) - a previously-reasoned, already-approved call, not an
 * oversight.
 *
 * Glow went through two rounds on this dashboard specifically. Track B1's
 * UI review first found only AI Pipeline reliably read as "premium" in
 * practice (AI Workforce's own conditional glow only lit up while an
 * agent was actually `running`, so it often looked identical to a plain
 * card), and extended the existing live-signal-only `glow` prop to two
 * more cards. A follow-up Track B1 UI refinement then replaced that
 * single-layer approach dashboard-wide with a two-layer system - see
 * Section 4.1's own updated text in
 * docs/architecture/m8-ui-ux-design-bible.md and Card.tsx's docstring
 * for the full mechanism:
 *
 *  - Ambient (always on): every one of the 17 dashboard cards now has
 *    its own persistent identity color at low opacity - KPI strip
 *    (royal-blue/cyan/amber/purple/orange/gold), World Map (indigo),
 *    Country Intelligence (emerald), AI Workforce (violet), AI Pipeline
 *    (purple), Sales Pipeline (blue), Pipeline Overview (teal), Today's
 *    Priorities (yellow), AI Recommendations (cyan), Mailbox Brief
 *    (orange), Activity (slate), Top Countries (emerald).
 *  - Active/breathing (conditional): only where a real, already-existing
 *    signal exists - Needs Review/AI Tasks Running/Open Conversations
 *    (KPI strip; Open Conversations gained a real signal in Track C1 -
 *    see that note below), World Map (any country with activity today),
 *    Country Intelligence (selected country has prospects), AI Workforce
 *    (an agent is running), AI Pipeline (has prospects), Today's
 *    Priorities (has items needing review). Deliberately NOT active on:
 *    Active Prospects/AI Confidence Score (no "event" distinct from
 *    "there is a number"), Revenue Pipeline (ambient-only - no backend
 *    signal exists yet to honestly drive `active` from; still pending
 *    Track C4), Sales Pipeline/Pipeline Overview/AI Recommendations/
 *    Mailbox Brief (honest "not implemented" placeholders - breathing
 *    would imply live activity that doesn't exist), Activity/Top
 *    Countries (ranked/historical snapshots, no single "happening right
 *    now" event).
 *
 * Track C1 (dashboard-capabilities-architecture-plan.md): Open
 * Conversations moved from an honest placeholder to real data - a new
 * GET .../conversations/count endpoint (app/api/routes/conversations.py)
 * backs KpiStrip's own count, and `active` now fires on
 * `count > 0`, exactly the "Unread Conversations -> Orange breathing
 * glow" behavior the CEO's original glow-system worked example named -
 * deferred at the time only because no backend signal existed yet, not
 * because the design was wrong.
 *
 * Glow retune (third Track B1 pass): real-browser feedback on the
 * two-layer system above called the ambient layer "too broad and
 * diffused... slightly hazy" and asked for the original single-layer
 * `glow` look (tight blur, visibly brighter) as the reference point.
 * Same `accent`/`active` props, same 17-card mapping - only the box-
 * shadow recipe changed, in Card.tsx: tighter blur/spread and higher
 * opacity for the always-on ambient layer, and `active`'s breathing peak
 * retuned to exactly 1.4x ambient's alpha (the requested "30-40%
 * brighter"). The breathing overlay is now always mounted rather than
 * conditionally rendered, so a card's `active` condition clearing fades
 * the glow back down smoothly instead of it disappearing on the same
 * frame - see Card.tsx's `activeGlowOverlayClassName` for the mechanism.
 *
 * Still true, unchanged from the prior pass: I cannot pixel-verify this
 * fits with zero scroll at 1920x1080 - `vite dev`/`vite build` don't run
 * in this sandbox. The `max-h-[46vh]` cap is a deliberate, load-bearing
 * fix for the exact problem reported, but it still needs your browser to
 * confirm.
 */
export default function CommandCenter() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const { prospects, isLoading: prospectsLoading } = useDashboardPortfolio();
  const { byName } = useCountryReference();
  const { geometry } = useWorldGeometry();
  const navigate = useNavigate();

  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);

  const countryAggregates = useMemo(() => aggregateByCountry(prospects), [prospects]);
  const effectiveCountry = selectedCountry ?? countryAggregates[0]?.country ?? null;

  const mapCountries: WorldMapCountry[] = useMemo(() => {
    const today = new Date();
    const isToday = (iso: string) => {
      const d = new Date(iso);
      return d.getUTCFullYear() === today.getUTCFullYear() && d.getUTCMonth() === today.getUTCMonth() && d.getUTCDate() === today.getUTCDate();
    };
    return countryAggregates.map((c) => ({
      ...c,
      hasActivityToday: prospects.some((p) => p.country === c.country && isToday(p.first_discovered_at)),
    }));
  }, [countryAggregates, prospects]);

  if (!companiesLoading && !activeCompanyId) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="max-w-md text-center">
          <h1 className="text-lg font-semibold text-slate-100">Select a business</h1>
          <p className="mt-2 text-sm text-slate-400">
            The Command Center is scoped to one business at a time. Choose one from the switcher, or add your first
            business to see real Discovery/Research data here.
          </p>
          <button
            onClick={() => navigate("/businesses/new")}
            className="mt-4 rounded-lg bg-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-accent-primary/90"
          >
            Add your business
          </button>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      {/* Top row — Command Strip: intrinsic height, never grows */}
      <section className="flex shrink-0 flex-col gap-1.5">
        <KpiStrip prospects={prospects} isLoading={prospectsLoading} />
        <TodaysSummaryCard prospects={prospects} isLoading={prospectsLoading} />
      </section>

      {/* Middle row — Global Command Deck: map is flex-1 but capped at
          ~46% of the viewport height, so it can never dominate. */}
      <section className="grid min-h-0 flex-1 grid-cols-1 gap-2 max-h-[46vh] xl:grid-cols-[2fr_1fr_1fr]">
        <div className="min-h-0">
          <WorldMap
            countries={mapCountries}
            selectedCountry={effectiveCountry}
            onSelectCountry={setSelectedCountry}
            geometry={geometry ?? undefined}
          />
        </div>
        <div className="min-h-0">
          {effectiveCountry ? (
            <CountryIntelligencePanel country={effectiveCountry} prospects={prospects} reference={byName(effectiveCountry)} />
          ) : (
            <Card padding="compact" className="flex h-full items-center justify-center text-center text-xs text-slate-500">
              Country Intelligence appears once prospects have a country.
            </Card>
          )}
        </div>
        <div className="min-h-0">
          <AiWorkforceStatusWidget />
        </div>
      </section>

      {/* Bottom row — Operational Deck: eight compact cards, all visible
          at once, no tabs. M8.7 Phase C restores Pipeline Overview
          (Design Bible Section 8 requires it; the M8.3 layout revision
          had dropped it from composition without removing the file) as
          an 8th column rather than a 2nd row - grid-cols-7 to
          grid-cols-8 only narrows each column, it does not add height,
          so the single-screen fix M8.3 fought hard to land is untouched. */}
      <section className="grid min-h-0 flex-1 grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-8">
        <AiPipelineWidget prospects={prospects} isLoading={prospectsLoading} />
        <SalesPipelineWidget />
        <PipelineFunnel />
        <TodaysPriorities prospects={prospects} isLoading={prospectsLoading} limit={3} compact />
        <AiRecommendations />
        <MailboxBrief />
        <ActivityTimeline prospects={prospects} isLoading={prospectsLoading} limit={4} compact />
        <TopPerformingCountries prospects={prospects} isLoading={prospectsLoading} limit={3} compact />
      </section>
    </div>
  );
}
