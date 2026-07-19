import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

/**
 * Card — M8.1 primitive, Design Bible Section 4.4 (Elevation) + 9.1
 * (every card on every page uses the same elevation/radius/border rules,
 * no page-local card style).
 *
 * `glow` is deliberately a distinct, opt-in prop from `elevated` -
 * Section 4.1's semantic rule ("glow means this element is live or
 * currently AI-touched right now") is enforced structurally here: a
 * plain resting Card can never accidentally pick up a glow just by
 * being elevated. A caller has to explicitly say `glow="ai"` (etc.),
 * which is the same deliberateness the Badge `tone` prop already
 * requires for AI-attribution color.
 *
 * `padding` (M8.3 single-screen polish) - "compact" is the dense variant
 * for the Command Center's operational row (7 small glanceable cards
 * that must all fit on one screen without scrolling). Deliberately a
 * prop ON Card, not a className override callers append - Tailwind's
 * generated stylesheet order isn't guaranteed to match source order, so
 * appending a conflicting `p-*` utility via `className` wouldn't reliably
 * win against Card's own base padding class. Living inside Card's own
 * conditional avoids that entirely. Defaults to "normal" (p-6,
 * unchanged) everywhere else in the app.
 */
export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  elevated?: boolean;
  glow?: "primary" | "ai" | "success" | "warning" | "danger" | false;
  padding?: "normal" | "compact";
  children: ReactNode;
}

type GlowTone = Exclude<CardProps["glow"], false | undefined>;

const GLOW_CLASSES: Record<GlowTone, string> = {
  primary: "shadow-glow-primary",
  ai: "shadow-glow-ai",
  success: "shadow-glow-success",
  warning: "shadow-glow-warning",
  danger: "shadow-glow-danger",
};

const PADDING_CLASSES: Record<NonNullable<CardProps["padding"]>, string> = {
  normal: "p-6",
  compact: "p-3",
};

export function Card({ elevated = false, glow = false, padding = "normal", className, children, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-card border border-border-hairline bg-surface-1",
        PADDING_CLASSES[padding],
        elevated ? "shadow-elevation-2" : "shadow-elevation-1",
        glow && GLOW_CLASSES[glow],
        className
      )}
      {...rest}
    >
      {children}
    </div>
  );
}
