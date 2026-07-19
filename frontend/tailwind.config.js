/** @type {import('tailwindcss').Config} */
// M8.1 — Design System Foundation. Token values below are the literal
// implementation of the M8 UI/UX Design Bible, Section 4 (Design System) —
// see docs/architecture/m8-ui-ux-design-bible.md. Nothing here is a
// stylistic guess: every named token maps to a specific role that document
// assigns it, so a future page never has a reason to reach for a raw hex
// value instead of a token.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Canvas / elevation — Design Bible 4.1 + 4.4. Deliberately a deep
        // blue-black, never pure #000000: the glow/accent effects the rest
        // of this system depends on need somewhere to visually bloom into,
        // which a true-black canvas doesn't give them (Section 4.1's own
        // explicit reasoning).
        surface: {
          0: "#0A0E17", // page canvas
          1: "#10141F", // resting card/panel
          2: "#171D2C", // nested/hovered content within a card
          3: "#1E2537", // floating (modal/palette/dropdown) — one step past 4.4's third elevation level
        },
        border: {
          hairline: "rgba(255, 255, 255, 0.08)",
          "hairline-strong": "rgba(255, 255, 255, 0.14)",
        },
        // Accent spectrum — derived from the recommended brand mark's own
        // blue→purple gradient (Design Bible Section 6), not chosen
        // independently of it.
        accent: {
          primary: "#2F7BFF", // primary actions, active nav, default map hotspots
          secondary: "#22D3EE", // secondary data series, links
          ai: "#8B5CF6", // fixed, semantic: ANY AI-attributed surface, everywhere, always this color (Section 4.1)
          "ai-soft": "#C4B5FD",
        },
        status: {
          success: "#22C55E",
          warning: "#F59E0B",
          danger: "#EF4444",
          info: "#38BDF8",
        },
      },
      fontFamily: {
        // Design Bible 4.2 — a single geometric/technical sans everywhere.
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      borderRadius: {
        card: "14px",
        pill: "999px",
      },
      boxShadow: {
        // Elevation (4.4) is lightness + hairline border, NOT drop shadow —
        // a shadow barely registers against a near-black canvas. These
        // three are the ONLY non-color elevation cue this system uses, and
        // they are deliberately faint.
        "elevation-1": "0 1px 0 0 rgba(255,255,255,0.02) inset",
        "elevation-2": "0 4px 16px -4px rgba(0,0,0,0.45)",
        "elevation-3": "0 12px 32px -8px rgba(0,0,0,0.55)",
        // Glow (4.1/4.5) is semantic, not decorative default: applied only
        // to elements that are genuinely live/active right now. Never
        // applied to a resting card just because it looks nice — see the
        // Design Bible's own explicit warning against over-applying this.
        "glow-primary": "0 0 0 1px rgba(47,123,255,0.4), 0 0 20px -2px rgba(47,123,255,0.45)",
        "glow-ai": "0 0 0 1px rgba(139,92,246,0.4), 0 0 20px -2px rgba(139,92,246,0.45)",
        "glow-success": "0 0 0 1px rgba(34,197,94,0.35), 0 0 16px -2px rgba(34,197,94,0.4)",
        "glow-warning": "0 0 0 1px rgba(245,158,11,0.35), 0 0 16px -2px rgba(245,158,11,0.4)",
        "glow-danger": "0 0 0 1px rgba(239,68,68,0.35), 0 0 16px -2px rgba(239,68,68,0.4)",
      },
    },
  },
  plugins: [],
};
