import { cn } from "../../design-system";

/**
 * CostPill — small, reusable inline currency display, used everywhere a
 * dollar figure appears in this zone (Provider cards, Activity table,
 * ApprovalCard). Renders with `tabular-nums` (a built-in Tailwind
 * utility, no config change needed) so a column of these lines up
 * cleanly - the one small typography rule the approved AI Gateway UI
 * architecture doc calls out as doing real work toward the requested
 * "Bloomberg Terminal" feel (Section 6.7).
 *
 * `null`/`undefined` renders an em-dash (matches KpiCard/PlaceholderNotice's
 * existing "no fabricated numbers" discipline) rather than "$0.00" or "$NaN".
 */
export function CostPill({ usd, className }: { usd: number | null | undefined; className?: string }) {
  if (usd === null || usd === undefined) {
    return <span className={cn("font-mono text-xs tabular-nums text-slate-500", className)}>—</span>;
  }
  return <span className={cn("font-mono text-xs tabular-nums text-slate-200", className)}>${usd.toFixed(4)}</span>;
}
