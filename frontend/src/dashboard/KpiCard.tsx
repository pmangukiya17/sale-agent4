import type { LucideIcon } from "lucide-react";
import { Construction, Inbox } from "lucide-react";
import { Card, cn } from "../design-system";
import type { AccentColor, PlaceholderKind } from "../design-system";

/**
 * KpiCard — reusable Zone 1 primitive (Design Bible Section 8: one KPI row,
 * each card = sparkline+delta). Deliberately reusable on Analytics too
 * (M8.9), per the milestone's architecture requirement - it takes only
 * primitive props (label/value/icon/delta/placeholderKind), it never
 * reaches into a hook or fetches anything itself.
 *
 * `placeholderKind` renders the value as an em-dash with a small,
 * distinctly-colored/iconed caption instead of a number - and, per the
 * M8.3 review, distinguishes WHY there's no number: "no-data" (the field
 * is real, e.g. AI Confidence Score before any prospect has been scored
 * yet) vs "not-implemented" (no backend capability exists at all, e.g. AI
 * Tasks Running/Open Conversations/Revenue Pipeline). Same icon+color
 * vocabulary as PlaceholderNotice.tsx, applied to the smaller KPI-card
 * footprint.
 *
 * `accent`/`active` (Track B1 UI refinement) - threaded straight through
 * to Card, same contract as everywhere else in the dashboard: `accent`
 * gives each of the six KPI cards its own persistent identity color even
 * at rest, `active` is the caller's job to only ever set from a real
 * signal (KpiStrip.tsx documents, per card, why each does or doesn't
 * have one - Open Conversations/Revenue Pipeline stay `active=false`
 * since no backend capability exists to drive a real signal from, same
 * honesty rule `placeholderKind` already enforces here).
 */
export interface KpiCardProps {
  label: string;
  value?: string | number;
  icon: LucideIcon;
  delta?: { value: string; positive: boolean };
  placeholderKind?: PlaceholderKind;
  placeholderReason?: string;
  accent?: AccentColor | false;
  active?: boolean;
}

const PLACEHOLDER_STYLES: Record<PlaceholderKind, { icon: typeof Inbox; text: string; caption: string }> = {
  "no-data": { icon: Inbox, text: "text-slate-500", caption: "text-slate-500" },
  "not-implemented": { icon: Construction, text: "text-slate-500", caption: "text-status-warning" },
};

export function KpiCard({
  label,
  value,
  icon: Icon,
  delta,
  placeholderKind,
  placeholderReason,
  accent = false,
  active = false,
}: KpiCardProps) {
  const isPlaceholder = Boolean(placeholderKind);
  const style = placeholderKind ? PLACEHOLDER_STYLES[placeholderKind] : null;
  const PlaceholderIcon = style?.icon;

  return (
    <Card padding="compact" accent={accent} active={active} className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</span>
        {isPlaceholder && PlaceholderIcon ? (
          <PlaceholderIcon className={cn("h-3.5 w-3.5", style?.caption)} aria-hidden="true" />
        ) : (
          <Icon className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
        )}
      </div>
      <div className="flex items-end justify-between">
        <span className={cn("text-xl font-semibold", isPlaceholder ? style?.text : "text-slate-100")}>
          {isPlaceholder ? "—" : value}
        </span>
        {!isPlaceholder && delta && (
          <span className={cn("text-[11px] font-medium", delta.positive ? "text-status-success" : "text-status-danger")}>
            {delta.positive ? "▲" : "▼"} {delta.value}
          </span>
        )}
      </div>
      {isPlaceholder && (
        <p className={cn("truncate text-[10px] font-medium", style?.caption)}>
          {placeholderKind === "no-data" ? "No data yet" : "Not yet implemented"}
        </p>
      )}
    </Card>
  );
}
