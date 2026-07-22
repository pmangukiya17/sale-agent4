import type { CSSProperties, HTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

/**
 * Card — M8.1 primitive, Design Bible Section 4.4 (Elevation) + 9.1
 * (every card on every page uses the same elevation/radius/border rules,
 * no page-local card style).
 *
 * `glow` is the ORIGINAL M8.1 mechanism and is UNCHANGED - still opt-in,
 * still strictly "this element is live/AI-touched right now" (Section
 * 4.1's original rule), still the only glow AgentCard.tsx (the
 * /ai-workforce roster page, outside the dashboard) uses. Kept exactly
 * as-is rather than folded into `accent`/`active` below, so that page's
 * behavior doesn't silently change as a side effect of a dashboard-scoped
 * request.
 *
 * `accent`/`active` are the Track B1 UI refinement's two-layer lighting
 * system, additive to `glow`, not a replacement of it:
 *  - `accent` (always-on, when set): a very low-opacity, large-blur,
 *    unanimated "ambient" glow that gives a card its own persistent
 *    color identity, present even at rest. This is a deliberate,
 *    explicit reversal of Section 4.1's original "glow only when live"
 *    rule - see that section's own updated text in
 *    docs/architecture/m8-ui-ux-design-bible.md for why, and Card's own
 *    git history for the fact that this reversal was requested, not
 *    discovered as a bug.
 *  - `active` (boolean, requires `accent`): layers a second, brighter
 *    version of the same accent color on top, with a slow (~3.5s)
 *    breathing opacity animation - "gentle," per the explicit "Apple
 *    Dynamic Island or Linear, not RGB keyboards" instruction, never a
 *    flash/pulse. This is the ONLY layer that is conditional on real
 *    activity; `accent` alone is decorative identity, `active` is what
 *    still carries the "something is genuinely happening" signal. A
 *    caller should never set `active` without a real, already-existing
 *    boolean condition behind it (see AiPipelineWidget.tsx etc. for the
 *    established pattern) - the honesty rule from `glow` carries over to
 *    this layer even though the ambient layer no longer needs it.
 *
 * Implementation note: `accent`'s ambient shadow and `active`'s brighter
 * overlay both derive from ONE rgb triplet per accent color (ACCENT_RGB
 * below), not from separate Tailwind box-shadow tokens per color per
 * state. A dozen-plus accent colors × 2 states would mean 24+ near-
 * duplicate `shadow-*` tokens in tailwind.config.js; instead, only a
 * single shared `animate-card-breathe` keyframe (opacity only) lives
 * there, and the actual color is an inline `boxShadow` computed here.
 * Same reasoning as this project's other "one shared primitive, not N
 * near-duplicates" decisions (ConfirmDialog/useDeleteResource, etc.).
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
  /** Always-on ambient identity glow - see this file's own docstring. */
  accent?: AccentColor | false;
  /** Upgrades `accent`'s ambient glow to a brighter, breathing state.
   * No-op without `accent` also being set. */
  active?: boolean;
  padding?: "normal" | "compact";
  children: ReactNode;
}

export type AccentColor =
  | "royal-blue"
  | "cyan"
  | "amber"
  | "purple"
  | "orange"
  | "gold"
  | "indigo"
  | "emerald"
  | "violet"
  | "blue"
  | "teal"
  | "yellow"
  | "slate";

// One rgb triplet per named accent - the full palette from the Track B1
// UI refinement request. Four deliberately reuse an EXISTING semantic
// color's exact rgb rather than inventing a visually-near-duplicate:
// amber = the same rgb as `glow-warning`, violet = the same rgb as
// `glow-ai`, blue = the same rgb as `glow-primary` - reusing, not
// duplicating, an already-established meaning where the two genuinely
// coincide (e.g. "AI Workforce" already meant accent-ai/violet before
// this change).
const ACCENT_RGB: Record<AccentColor, string> = {
  "royal-blue": "37,99,235",
  cyan: "6,182,212",
  amber: "245,158,11",
  purple: "168,85,247",
  orange: "249,115,22",
  gold: "212,175,55",
  indigo: "99,102,241",
  emerald: "16,185,129",
  violet: "139,92,246",
  blue: "47,123,255",
  teal: "20,184,166",
  yellow: "234,179,8",
  slate: "226,232,240",
};

/**
 * Exported so non-Card elements can apply the exact same ambient/active
 * glow recipe Card itself uses - specifically WorldMap.tsx, which isn't
 * a Card (it fills whatever box its parent gives it, reused on pages
 * that may not wrap it in one) but still needs an "World Map = indigo"
 * identity per the same Track B1 request. One recipe, two call sites,
 * not two copies of the same box-shadow math.
 */
export function ambientGlowStyle(accent: AccentColor): CSSProperties {
  return { boxShadow: `0 0 32px -4px rgba(${ACCENT_RGB[accent]},0.13)` };
}

export function activeGlowStyle(accent: AccentColor): CSSProperties {
  return { boxShadow: `0 0 40px -2px rgba(${ACCENT_RGB[accent]},0.38)` };
}

/** className for the absolutely-positioned breathing overlay - pair with
 * an inline `style={activeGlowStyle(accent)}` on the same element. Does
 * NOT include a border-radius utility: Card uses `rounded-card`, but
 * WorldMap.tsx's own wrapper uses `rounded-lg` - the caller appends
 * whichever radius already matches its own container so the glow's
 * corners line up with the element it's actually glowing around. */
export const ACTIVE_GLOW_OVERLAY_CLASSNAME =
  "pointer-events-none absolute inset-0 animate-card-breathe motion-reduce:animate-none motion-reduce:opacity-90";

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

export function Card({
  elevated = false,
  glow = false,
  accent = false,
  active = false,
  padding = "normal",
  className,
  children,
  style,
  ...rest
}: CardProps) {
  // Ambient: always visible when `accent` is set, 10-15% opacity, large
  // blur, no ring/border component (a crisp inset ring reads as an
  // outline, not a "soft edge glow") - applied as this card's own
  // box-shadow directly, not an overlay, since it never animates.
  const ambientStyle = accent ? ambientGlowStyle(accent) : undefined;

  return (
    <div
      className={cn(
        "relative rounded-card border border-border-hairline bg-surface-1",
        PADDING_CLASSES[padding],
        elevated ? "shadow-elevation-2" : "shadow-elevation-1",
        glow && GLOW_CLASSES[glow],
        className
      )}
      style={accent ? { ...ambientStyle, ...style } : style}
      {...rest}
    >
      {children}
      {accent && active && (
        <div aria-hidden="true" className={cn(ACTIVE_GLOW_OVERLAY_CLASSNAME, "rounded-card")} style={activeGlowStyle(accent)} />
      )}
    </div>
  );
}
