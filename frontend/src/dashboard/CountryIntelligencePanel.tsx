import { useMemo, useState } from "react";
import { Globe2 } from "lucide-react";
import { Card, Badge, PlaceholderNotice } from "../design-system";
import type { DashboardProspect } from "./useDashboardPortfolio";
import type { CountryReference } from "./useCountryReference";
import { averageScore } from "./selectors";

/**
 * CountryIntelligencePanel — reusable companion to WorldMap (Design Bible
 * Section 8's tiering: always-visible / primary no-scroll / secondary
 * scrollable / deep-dive expand). Built to be reused as-is on Discovery
 * and Research pages (same props: a country name + that country's prospect
 * slice + optional reference row), not something this dashboard hardcodes.
 *
 * Tier-by-tier honesty:
 *  - Always-visible: name (real), local time (real, computed from the
 *    backend Country.default_timezone when the reference lookup matches -
 *    otherwise omitted, never guessed), opportunity badge (real, prospect
 *    count > 0).
 *  - Primary metrics (no-scroll): prospect count, average score, needs-
 *    review count - all real, all already-fetched Prospect data.
 *  - Secondary (scrollable): industry breakdown - real, from
 *    Prospect.industry_raw.
 *  - Deep-dive (expand): trade insights / economic indicators - HONEST
 *    placeholder. No backend model holds macro country-level trade or
 *    economic data (Country only has code/name/region/timezone - see
 *    useCountryReference.ts) - fabricating numbers here would violate the
 *    "no fabricated data" requirement, so this tier states the gap plainly
 *    instead.
 *
 * Track B1 UI review (superseded by the follow-up two-layer lighting
 * refinement below, kept here for history): originally shipped as
 * `glow="success"`, mirroring this card's own "Active" Badge signal.
 *
 * Track B1 UI refinement (two-layer lighting system): migrated to
 * `accent="emerald"` (ambient, always on - Country Intelligence's
 * persistent identity color) + `active={slice.length > 0}` (the same
 * real signal the old `glow="success"` used, now the brighter breathing
 * layer instead of the only layer). Card's `glow` prop itself still
 * exists and is unchanged elsewhere (see Card.tsx's own docstring) - this
 * card just moved off it onto the newer system, it wasn't deprecated.
 */
export function CountryIntelligencePanel({
  country,
  prospects,
  reference,
}: {
  country: string;
  prospects: DashboardProspect[];
  reference: CountryReference | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const slice = useMemo(() => prospects.filter((p) => p.country === country), [prospects, country]);
  const avg = averageScore(slice);
  const needsReview = slice.filter((p) => p.status === "scored" || p.status === "in_review").length;

  const industries = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of slice) {
      if (!p.industry_raw) continue;
      counts.set(p.industry_raw, (counts.get(p.industry_raw) ?? 0) + 1);
    }
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [slice]);

  const localTime = useMemo(() => {
    if (!reference?.default_timezone) return null;
    try {
      return new Intl.DateTimeFormat("en-US", {
        timeZone: reference.default_timezone,
        hour: "numeric",
        minute: "2-digit",
      }).format(new Date());
    } catch {
      return null;
    }
  }, [reference]);

  return (
    <Card
      padding="compact"
      accent="emerald"
      active={slice.length > 0}
      className="flex h-full flex-col gap-2.5 overflow-y-auto"
    >
      <div className="flex items-center justify-between">
        <div className="flex min-w-0 items-center gap-1.5">
          <Globe2 className="h-3.5 w-3.5 shrink-0 text-accent-primary" aria-hidden="true" />
          <h3 className="truncate text-xs font-semibold text-slate-100">{country}</h3>
        </div>
        {slice.length > 0 && <Badge tone="success">Active</Badge>}
      </div>

      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
        {localTime && <span>{localTime} local</span>}
        {reference?.region && <span>{reference.region}</span>}
        {!reference && <span>No reference match yet.</span>}
      </div>

      <dl className="grid grid-cols-3 gap-2 text-center">
        <div>
          <dt className="text-[10px] text-slate-500">Prospects</dt>
          <dd className="text-base font-semibold text-slate-100">{slice.length}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-slate-500">Avg Score</dt>
          <dd className="text-base font-semibold text-slate-100">{avg !== null ? avg.toFixed(0) : "—"}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-slate-500">Review</dt>
          <dd className="text-base font-semibold text-slate-100">{needsReview}</dd>
        </div>
      </dl>

      {industries.length > 0 && (
        <div>
          <h4 className="mb-1 text-[10px] font-medium uppercase tracking-wide text-slate-500">Industries</h4>
          <div className="max-h-16 space-y-0.5 overflow-y-auto pr-1">
            {industries.map(([name, count]) => (
              <div key={name} className="flex justify-between text-[11px] text-slate-400">
                <span className="truncate">{name}</span>
                <span className="text-slate-500">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <button
        onClick={() => setExpanded((v) => !v)}
        className="text-left text-[11px] font-medium text-accent-primary hover:underline"
      >
        {expanded ? "Hide" : "Show"} market intelligence
      </button>
      {expanded && (
        <PlaceholderNotice reason="Trade flows and economic indicators aren't available yet - no macro trade/economic data model exists." />
      )}
    </Card>
  );
}
