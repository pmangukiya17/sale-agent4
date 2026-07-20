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
        // M8.7 Phase F — contrast audit (Design Bible Section 12: "all body
        // text against surface-0/surface-1 must meet WCAG AA (4.5:1),
        // tested against the actual rendered surface color"). Tailwind's
        // stock slate-500 (#64748b) is this app's most-used "muted
        // caption/secondary text" color (~145 call sites) but measures
        // only ~4.05:1 on surface-0 and ~3.87:1 on surface-1 - a real,
        // silent AA failure at normal text sizes, not caught until this
        // audit because each individual usage "looked fine" in isolation
        // (exactly the failure mode Section 12 warns about). Overriding
        // the token here - rather than hand-editing ~145 call sites -
        // fixes every consumer at once and keeps "slate-500 means muted
        // text" a single, checkable fact instead of ~145 independent
        // ones. #728299 keeps the same cool-gray hue family as the
        // default (100,116,139), lightened just enough to clear 4.5:1
        // against both surface-0 (~4.94:1) and surface-1 (~4.70:1).
        slate: {
          500: "#728299",
        },
      },
      fontFamily: {
        // Design Bible 4.2 — a single geometric/technical sans everywhere.
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      // Design Bible 4.2 — "a restrained 6-7 step type scale (display,
      // h1-h3, body, caption, micro-label), reused everywhere rather than
      // each module inventing its own sizes." Added M8.7 Phase A - the one
      // token category from Section 4 that M8.1 hadn't landed yet (every
      // page until now used raw Tailwind text-sm/text-xs/etc. sizes
      // directly). Each entry is a [size, {lineHeight}] pair, not a bare
      // number, so line-height is never left to Tailwind's default and
      // silently inconsistent between two components using the same size.
      fontSize: {
        display: ["2.25rem", { lineHeight: "1.15" }],
        h1: ["1.875rem", { lineHeight: "1.2" }],
        h2: ["1.5rem", { lineHeight: "1.25" }],
        h3: ["1.25rem", { lineHeight: "1.3" }],
        body: ["0.875rem", { lineHeight: "1.5" }],
        caption: ["0.75rem", { lineHeight: "1.4" }],
        "micro-label": ["0.6875rem", { lineHeight: "1.3", letterSpacing: "0.04em" }],
      },
      borderRadius: {
        card: "14px",
        pill: "999px",
      },
      // Design Bible 5 — Motion System. Durations named by the same
      // category language that section uses (interaction / state-change),
      // not generic fast/slow labels, so a call site's class name states
      // *why* the duration was chosen. Added M8.7 Phase A - Section 5's
      // own values existed only as prose (e.g. "~200ms", "300-400ms")
      // until now, with nothing in tailwind.config.js to check them
      // against.
      transitionDuration: {
        interaction: "160ms", // Section 5 "Animate on interaction": 120-200ms, feedback not storytelling
        tick: "200ms", // Section 5 "Animate on change": KPI count-up/down
        "state-change": "350ms", // Section 5 "Animate on change": agent status transition, 300-400ms
      },
      transitionTimingFunction: {
        // Calm, confident easing (ease-in-out, not a bounce/spring) -
        // matches Section 1's "communicate confidence, not constant
        // movement" identity statement and Section 11's ban on
        // decorative motion; one curve reused everywhere rather than a
        // different easing per component.
        standard: "cubic-bezier(0.4, 0, 0.2, 1)",
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
