import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card } from "../design-system";
import { useCompanies } from "../companies/CompanyContext";
import { useDashboardPortfolio, useLegacyCompanyStages } from "../dashboard/useDashboardPortfolio";
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
 *   - Bottom row (`flex-1 min-h-0`): seven compact cards in one dense
 *     grid (AI Pipeline, Sales Pipeline, Priorities, Recommendations,
 *     Mailbox Brief, Activity, Top Countries) - all visible
 *     simultaneously, not behind tabs. Because the middle row's height is
 *     now capped, this row reliably gets the space it needs instead of
 *     being squeezed off-screen.
 * Every widget here uses Card's new `padding="compact"` variant (see
 * Card.tsx) and, where applicable, a `limit`/`compact` prop to show fewer
 * rows - same components, same data, denser presentation only.
 *
 * Glass/glow: kept restrained to Design Bible Section 4.5's rule (glass
 * for overlays only - command palette, modals; NOT standing dashboard
 * cards) rather than applying frosted glass broadly - that's a
 * previously-reasoned, already-approved call, not an oversight. Ambient
 * glow (Card's `glow` prop) is pushed harder here instead: the map's live
 * markers, the AI Pipeline/AI Workforce cards when there's real activity.
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
  const { companies, isLoading: legacyLoading } = useLegacyCompanyStages();
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

      {/* Bottom row — Operational Deck: seven compact cards, all visible
          at once, no tabs. */}
      <section className="grid min-h-0 flex-1 grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-7">
        <AiPipelineWidget prospects={prospects} isLoading={prospectsLoading} />
        <SalesPipelineWidget />
        <TodaysPriorities prospects={prospects} isLoading={prospectsLoading} limit={3} compact />
        <AiRecommendations />
        <MailboxBrief />
        <ActivityTimeline prospects={prospects} isLoading={prospectsLoading} limit={4} compact />
        <TopPerformingCountries prospects={prospects} isLoading={prospectsLoading} limit={3} compact />
      </section>
    </div>
  );
}
