import { useState } from "react";
import type { ReactNode } from "react";
import { cn } from "./cn";

/**
 * Tooltip — M8.7 Phase D primitive, Design Bible Section 4.6.
 *
 * Deliberately a simple, CSS-positioned tooltip (absolutely positioned
 * relative to its trigger, shown on hover/focus), not a floating-ui/
 * popper-style dynamic-placement system - this project has no such
 * library installed, and a fixed `side` prop covers this dashboard's
 * actual real usage (a short label above an icon-only button, a
 * truncated value's full text) without pulling in new dependencies for
 * viewport-collision-aware repositioning nothing here currently needs.
 * If a future page genuinely needs edge-aware auto-flipping, that's a
 * deliberately separate, heavier addition - named here so it isn't
 * mistaken for an oversight (same disclosed-simplification shape as
 * Select's own docstring).
 *
 * Shown on both hover AND focus (`onFocus`/`onBlur`, not just
 * `onMouseEnter`/`onMouseLeave`) so a keyboard user tabbing to the
 * trigger sees the same content a mouse user would - Section 12's own
 * "every interactive element" accessibility rule applied here, not just
 * to a visible focus ring.
 */
export interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  className?: string;
}

const SIDE_CLASSES: Record<NonNullable<TooltipProps["side"]>, string> = {
  top: "bottom-full left-1/2 mb-2 -translate-x-1/2",
  bottom: "top-full left-1/2 mt-2 -translate-x-1/2",
  left: "right-full top-1/2 mr-2 -translate-y-1/2",
  right: "left-full top-1/2 ml-2 -translate-y-1/2",
};

export function Tooltip({ content, children, side = "top", className }: TooltipProps) {
  const [visible, setVisible] = useState(false);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      {children}
      {visible && (
        <span
          role="tooltip"
          className={cn(
            "pointer-events-none absolute z-50 whitespace-nowrap rounded-lg border border-border-hairline-strong bg-surface-3 px-2 py-1 text-caption text-slate-100 shadow-elevation-2",
            SIDE_CLASSES[side],
            className
          )}
        >
          {content}
        </span>
      )}
    </span>
  );
}
