import { cn } from "./cn";

/**
 * StatusIndicator — M8.1 primitive, Design Bible Section 5 (the named
 * agent/workflow state vocabulary) + Section 12 ("color is never the
 * only signal" - every status is a colored dot AND a text label, never
 * color alone).
 *
 * This is the fixed, system-wide status vocabulary from Section 5,
 * including the explicit note there that most of these map to the SAME
 * underlying backend fact (AgentOutcome/ActionOutcome/WorkflowInstanceStatus)
 * and differ only in which verb a page chooses to display - this
 * component takes that already-resolved label as `label` and only owns
 * the color+motion mapping for the smaller set of underlying states.
 *
 * Motion rule, straight from Section 5's "always alive" vs "static by
 * design" split: only genuinely ACTIVE states (running/waiting/thinking-
 * shaped work) get the slow ambient pulse. Terminal states (completed,
 * failed) never pulse - nothing is still happening, so nothing should
 * look like it is. Reusing this one component everywhere is what makes
 * that rule automatically consistent instead of something every page has
 * to remember to apply itself.
 *
 * Uses Tailwind's built-in `animate-pulse` (a calm opacity fade, ~2s) for
 * the ambient dot rather than `animate-ping`'s sharper scale-and-fade -
 * Section 5's own calibration note is explicit that ambient motion has to
 * be slow/low-contrast enough to recede into peripheral awareness, not
 * compete for attention, and a ping-style ring reads as far too "busy"
 * across a whole roster of simultaneously active agent cards.
 */
export type StatusKind = "active" | "waiting" | "success" | "failed" | "idle" | "paused";

export interface StatusIndicatorProps {
  kind: StatusKind;
  label: string;
  className?: string;
}

const KIND_STYLES: Record<StatusKind, { dot: string; text: string; pulse: boolean }> = {
  active: { dot: "bg-status-info", text: "text-status-info", pulse: true },
  waiting: { dot: "bg-status-warning", text: "text-status-warning", pulse: true },
  success: { dot: "bg-status-success", text: "text-status-success", pulse: false },
  failed: { dot: "bg-status-danger", text: "text-status-danger", pulse: false },
  idle: { dot: "bg-slate-500", text: "text-slate-400", pulse: false },
  // No backend equivalent exists yet for a genuinely paused workflow (see
  // Design Bible Section 5 + Section 14) - rendered distinctly (amber
  // outline, no fill, no pulse) so it never visually reads as "actively
  // running" or "waiting on something real" when what it actually means
  // is "no backend capability behind this yet."
  paused: { dot: "bg-transparent border border-status-warning", text: "text-status-warning", pulse: false },
};

export function StatusIndicator({ kind, label, className }: StatusIndicatorProps) {
  const style = KIND_STYLES[kind];
  return (
    <span className={cn("inline-flex items-center gap-2 text-sm font-medium", style.text, className)}>
      <span className={cn("inline-flex h-2 w-2 rounded-full", style.dot, style.pulse && "animate-pulse")} />
      {label}
    </span>
  );
}
