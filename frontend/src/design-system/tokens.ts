/**
 * Raw token values — M8.1. The same palette defined in tailwind.config.js,
 * exported as plain constants for the cases a Tailwind class name can't
 * reach: chart color scales (Recharts/whatever charting library M8.9
 * settles on - Design Bible Section 14 - takes raw color strings, not
 * classNames), the World Map's hotspot/arc colors, and any inline SVG.
 *
 * This file must be kept in sync with tailwind.config.js's `theme.extend.
 * colors` block by hand - there are exactly two places these values live,
 * deliberately (a Tailwind class needs the config; anything rendered
 * outside Tailwind's own class pipeline needs a real JS value), not
 * because a third abstraction was skipped.
 */
export const colors = {
  surface: {
    0: "#0A0E17",
    1: "#10141F",
    2: "#171D2C",
    3: "#1E2537",
  },
  border: {
    hairline: "rgba(255, 255, 255, 0.08)",
    hairlineStrong: "rgba(255, 255, 255, 0.14)",
  },
  accent: {
    primary: "#2F7BFF",
    secondary: "#22D3EE",
    ai: "#8B5CF6",
    aiSoft: "#C4B5FD",
  },
  status: {
    success: "#22C55E",
    warning: "#F59E0B",
    danger: "#EF4444",
    info: "#38BDF8",
  },
} as const;
