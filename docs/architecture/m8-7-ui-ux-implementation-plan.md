# M8.7 — UI/UX Design Bible: Implementation Plan

**Status: plan only. Not authorized for implementation.** This document
describes *how* the already-approved architecture
(`m8-ui-ux-design-bible.md`, including its M8.7 amendments — Section
9.2 refactor-in-place migration method, Section 10.1 Design Debt Budget)
will actually get built. No new component, no page rewrite, nothing
described below has been written as part of producing this plan.

**The single most important fact this plan is built around: M8.7 is not
starting from zero.** M8.1 (Design System Foundation), M8.2 (Application
Shell & Navigation), M8.3 (Command Center / dashboard), and M8.4 (AI
Workforce) already implemented large parts of what the Design Bible
specifies — inspected directly against the real repository before
writing this plan, not assumed:

- `frontend/tailwind.config.js` already has the full color palette
  (surface/border/accent/status), radius, and elevation/glow tokens from
  Section 4.1/4.4/4.5, with comments citing the exact Design Bible
  section each value implements.
- `frontend/src/design-system/` already has a real barrel-exported
  primitive tier: `Button`, `Badge`, `Card` (with a `padding` variant),
  `Input`, `StatusIndicator`, `Tabs`, plus `tokens.ts` (raw JS values for
  non-Tailwind consumers) and `cn.ts`.
- `Sidebar.tsx`, `TopCommandStrip.tsx`, and `CommandPalette.tsx` already
  implement Section 3's navigation architecture and are already wired to
  real backend data (M8.5/M8.6 notifications, in particular).
- `CommandCenter.tsx` and its dashboard modules (`WorldMap`,
  `CountryIntelligencePanel`, `AiWorkforceStatusWidget`, `KpiStrip`,
  `ActivityTimeline`, and the rest of `frontend/src/dashboard/`) already
  implement Section 8's Command Center architecture, including the
  single-screen layout correction from the M8.3 layout revision.
- `AIWorkforce.tsx` and `frontend/src/ai-workforce/` already implement
  the Agent card / roster / trace pattern from Section 9's page catalog
  and Section 10's Agent card spec.

**What has genuinely not happened yet**, confirmed by direct inspection:
no `fontSize` type scale or motion-duration/easing tokens exist in
`tailwind.config.js` (Section 4.2/5's values are documented in prose only
so far); `design-system/` has no `Select`, `Table`, `Modal`, `Toast`, or
`Tooltip` yet, so Section 4.6's full component catalog is incomplete;
and — the largest real gap — eighteen existing pages
(`Businesses.tsx`, `Contacts.tsx`, `Pipeline.tsx`, `Prospects.tsx`,
`DiscoveryJobs.tsx`, `DiscoverySearches.tsx`, `ResearchJobs.tsx`,
`ProspectResearch.tsx`, `ProspectStrategy.tsx`, `ProspectOutreach.tsx`,
`PersonalizationJobs.tsx`, `OutreachPlaybooks.tsx`,
`CompanyProducts.tsx`, `CompanyICP.tsx`, `CompanyKnowledgeBase.tsx`,
`CompanyProfileEditor.tsx`, `WorkspaceSettingsPage.tsx`,
`BusinessEmailSignature.tsx`, `Settings.tsx`, and all five files under
`delivery/`) are still plain, unstyled Tailwind — exactly the state the
Design Bible's own "Grounding disclosure" described before M8.1 began,
unchanged since. This is Section 9.1's "hard requirement, not an
aspiration" not yet met for the large majority of the product's actual
page count.

This plan's phases are therefore weighted accordingly: Phases A–C are
short, mostly-confirmation passes over work that already exists; Phase D
fills a real, small, specific gap; Phase E — the page migration — is
where most of the remaining implementation effort actually is, and is
broken into its own sub-phases by IA zone so it stays reviewable in the
CEO's own requested increments, not one pass over eighteen files.

---

## Implementation Phases

### Phase A — Tokens: close the gap, don't rebuild

- **Objective:** land the two token categories Section 4 specifies that
  don't exist yet (type scale, motion durations/easing), without
  touching the color/radius/elevation tokens already shipped in M8.1.
- **Files/modules:** `frontend/tailwind.config.js` (`theme.extend.
  fontSize` — the 6–7 step scale from Section 4.2: display, h1–h3, body,
  caption, micro-label, each with a fixed line-height pair, not a bare
  size number; `theme.extend.transitionDuration` /
  `theme.extend.transitionTimingFunction` — the concrete durations
  Section 5 already names in prose: ~120–200ms interaction, ~200ms KPI
  tick, ~300–400ms state transition); `frontend/src/design-system/
  tokens.ts` (mirror the same values as raw JS constants, per that
  file's own documented "kept in sync by hand, two places on purpose"
  rule).
- **Expected outcome:** every token category the CEO's M8.7 review
  listed (Colors, Typography, Spacing, Radius, Elevation, Borders,
  Motion durations/easing) has a real, checkable value in
  `tailwind.config.js` — not just some of them.
- **Dependencies:** none (additive to the existing M8.1 config).
- **One cleanup this phase should also do, caught while grounding this
  plan in the real repo:** `frontend/src/pages/DesignSystemPreview.tsx`
  is still present, and its own docstring says plainly it's "TEMPORARY,
  M8.1-ONLY," to be removed "once M8.2+ has real pages exercising these
  primitives inside actual navigation." M8.2 (Sidebar/TopCommandStrip),
  M8.3 (Command Center), and M8.4 (AI Workforce) have all since landed
  and do exactly that — the file's own stated removal condition is
  already true today, independent of this plan. Phase A removes it (and
  its route in `App.tsx`) rather than extending it into a permanent
  component-catalog page, per the Design Debt Budget's "don't add a
  second competing pattern" spirit applied to pages, not just
  components — a real, already-navigable page is the living proof a new
  token/primitive works, not a dedicated showcase route.
- **Verification:** `tsc -b` (tokens.ts stays valid TypeScript, and the
  build stays clean with `DesignSystemPreview.tsx`'s route removed from
  `App.tsx`).

### Phase B — Shell audit: Sidebar, TopCommandStrip, navigation

- **Objective:** confirm — not rebuild — that the already-shipped
  application shell complies with the Design Bible as now amended
  (Section 9.2, Section 10.1), and close any small, specifically-named
  gaps found.
- **Files/modules:** `Sidebar.tsx`, `TopCommandStrip.tsx`,
  `CommandPalette.tsx`, `navConfig.ts` — read against Section 2
  (Information Architecture: four zones) and Section 3 (Navigation
  Architecture) line by line.
- **Expected outcome:** a short, written audit (added as a dated note in
  this file's own changelog, not a new document) listing: which parts of
  Sections 2/3 the current shell already satisfies, and which specific,
  named gaps (if any) exist — e.g. whether the four-zone grouping
  (Command Center / AI Workforce / CRM / Intelligence) is fully reflected
  in `navConfig.ts` today, given `navConfig.ts` predates the zone
  structure being finalized. Any gap found is fixed as a scoped edit to
  the existing files, per Section 9.2's refactor-in-place rule — not a
  shell rewrite.
- **Dependencies:** Phase A (if any nav-adjacent styling references the
  new tokens).
- **Verification:** `tsc -b`; manual nav-by-nav check against Section 2's
  zone table.

### Phase C — Dashboard audit: Command Center

- **Objective:** same audit-first approach as Phase B, applied to
  `CommandCenter.tsx` and `frontend/src/dashboard/` against Section 8.
- **Files/modules:** `CommandCenter.tsx` and its constituent widgets.
- **Expected outcome:** written confirmation of which Section 8
  requirements are already met (single-screen layout, KPI strip, World
  Map + Country Intelligence + AI Workforce status row, the seven-widget
  bottom row) and an explicit list of anything Section 8 asks for that
  isn't live yet (e.g. any chart type from Section 4.6 not yet used, or
  a widget still in a placeholder state per M8.3's own honesty rule —
  cross-checked against that milestone's own disclosed gaps rather than
  re-discovered from scratch).
- **Dependencies:** Phase A.
- **Verification:** `tsc -b`; re-run of `PlaceholderNotice`/placeholder-
  kind checks already established in M8.3 to confirm nothing regressed.

### Phase D — Component library: fill the real gap

- **Objective:** build the primitives Section 4.6's catalog specifies
  that don't exist yet, so Phase E's page migration has real components
  to migrate *into* rather than each page inventing its own — the
  Design Debt Budget (Section 10.1) applies from this phase onward:
  each of these is built once, as the canonical version, not per-page.
- **Files/modules:** `frontend/src/design-system/Select.tsx` (dropdown/
  multi-select per Section 4.6), `Table.tsx` (dense table shell: sortable
  header, sticky header, row hover, status/badge cells — the shape every
  List template in Section 9 needs), `Modal.tsx`, `Toast.tsx`,
  `Tooltip.tsx`; updates to `design-system/index.ts`'s barrel export for
  each.
- **Expected outcome:** Section 4.6's full component catalog exists in
  `design-system/`, each with the documented states (default, hover,
  focus-visible, disabled, loading where applicable) — no page-specific
  variant of any of these should be written after this phase.
- **Dependencies:** Phase A (these consume the token set directly, and
  removes the temporary preview page rather than reviving it — see
  Phase A's own note).
- **Verification:** `tsc -b`; each new primitive is proven by its first
  real consumer in Phase E, not by a dedicated showcase page (per the
  Design Debt Budget applied to pages, same reasoning as Phase A).

### Phase E — Page migration (the real bulk of this milestone)

Per the CEO's own instructions (phased, not one giant rewrite; migrate
in place per Section 9.2), this phase is itself split into sub-phases by
IA zone (Section 2's table), each independently reviewable and shippable
on its own:

- **E1 — CRM zone:** `Businesses.tsx`, `Contacts.tsx`, `Pipeline.tsx`,
  `Prospects.tsx`, `CompanyProducts.tsx`, `CompanyProfileEditor.tsx`.
  Highest-value first per the Design Bible's own Section 9.1 callout
  that Companies/Contacts are "most at risk of defaulting to a generic
  CRUD treatment."
- **E2 — AI Workforce zone (remaining pages):** `DiscoveryJobs.tsx`,
  `DiscoverySearches.tsx`, `ResearchJobs.tsx`, `ProspectResearch.tsx`,
  `ProspectStrategy.tsx`, `ProspectOutreach.tsx`,
  `PersonalizationJobs.tsx`, `OutreachPlaybooks.tsx` (`AIWorkforce.tsx`
  itself is already done — Phase C confirms, doesn't redo).
  `delivery/*` (Mailbox Brief / provider connections) included here per
  Section 2's reconciliation table.
- **E3 — Settings zone:** `CompanyICP.tsx`, `CompanyKnowledgeBase.tsx`,
  `WorkspaceSettingsPage.tsx`, `BusinessEmailSignature.tsx`,
  `Settings.tsx`. Per Section 9.1's own explicit guidance: same premium
  spacing budget as the Command Center, calmer motion (little to
  animate), never plainer.
- **E4 — Auth shell:** `Login.tsx`, `OAuthCallback.tsx` — per Section
  2's reconciliation table, "unchanged, restyled only."

- **Objective (each sub-phase):** refactor the listed pages in place
  (Section 9.2) to use Phase D's component library and Phase A's tokens,
  satisfying every row of Section 9.1's DNA-inheritance table, without
  changing existing data-fetching/mutation logic except where the IA
  reshuffle (Section 2) specifically requires it.
- **Expected outcome (each sub-phase):** the listed pages pass Section
  9.1's table (checked row by row, same as Section 9.1's own "evaluated
  against this table before it ships" instruction) and use zero
  page-local button/card/badge/table/modal/loading/empty-state
  implementations per the Design Debt Budget.
- **Dependencies:** Phase D (and Phase A transitively).
- **Verification (each sub-phase):** `tsc -b`; a grep-based Design Debt
  Budget check (no new `<button className=` /ad-hoc modal/table markup
  introduced where a Phase D primitive already covers it); manual
  before/after screenshot comparison is NOT possible from this sandbox
  (no browser) — same disclosed limitation as every prior frontend
  milestone, real visual confirmation needs the CEO's own environment.

### Phase F — Motion, polish, accessibility

- **Objective:** a final cross-cutting pass, only after Phases A–E are
  in place — matching the CEO's own ordering (motion/polish/
  accessibility last, not threaded through every earlier phase
  piecemeal, which would make each earlier phase's review harder to
  reason about in isolation).
- **Files/modules:** touches many files, but only for four specific,
  checkable things: (1) every category-1 "always alive" animation
  (Section 5) has a working `prefers-reduced-motion` static equivalent;
  (2) every interactive element has a visible `focus-visible` ring
  (Section 12); (3) Activity Timeline and the notification bell are
  real `aria-live="polite"` regions; (4) a contrast audit of body text
  against actual rendered surface color (Section 12), including glass/
  opacity stacking, not nominal token values in isolation.
- **Expected outcome:** Section 12's checklist is verifiably true across
  the whole app, not just the Command Center.
- **Dependencies:** Phases A–E.
- **Verification:** `tsc -b`; a written accessibility checklist per
  page (this plan does not assume a browser-based automated a11y tool
  is available in this sandbox — that remains the CEO's own environment
  to run, same disclosed limitation as every prior milestone's browser-
  dependent verification).

---

## Design Debt Budget enforcement (applies from Phase D onward)

Per Section 10.1: before any phase from D onward introduces a new
component, the working question is "which existing tier-1/tier-2
component does this replace, and why did it not work" — never "does this
look right for this one page." A running list of the canonical
implementation for each of the seven systems Section 10.1 names (button,
modal, table, card, badge, empty-state, loading-state) is maintained in
`design-system/index.ts`'s own barrel export — if a page-level component
ever duplicates one of these seven, that is a defect against this plan,
flagged and fixed in the same phase it's found, not deferred.

---

## What this plan deliberately does not cover

- **Final production logo/brand asset production** — Design Bible
  Section 14, still deferred, not part of any phase above.
- **2D vs. 3D world map technology change** — out of scope; the existing
  2D implementation (Phase C confirms, doesn't touch) stands.
- **Wiring AI Workforce/Activity Timeline to the M8.6 real-time stream**
  — explicitly deferred per M8.6's own disclosed scope boundary; those
  domains don't publish real platform Events yet. Not part of this plan.
- **A charting library swap** — Design Bible Section 14 leaves the
  specific library as an implementation decision; whatever is already in
  use for the funnel/line/bar/donut charts in `dashboard/` continues to
  be used, per the Design Debt Budget's "one canonical implementation"
  rule, unless a phase above finds a real gap it can't fill.
