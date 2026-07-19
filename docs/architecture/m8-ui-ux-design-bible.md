# M8 — UI/UX Architecture & Design Bible

**Status:** proposal only, produced before implementation, exactly like
every architecture document that preceded it in this project (see
`README.md` in this directory). Nothing in this document is authorized
for implementation. No React code, no components, no pages have been
written as part of producing it. It is the visual/experiential
counterpart to what `m7-workflow-engine-plan.md` and its siblings were
for the backend: the thing implementation gets checked against, not a
mood board.

**Inputs to this document:** nine dashboard concept images, AI-generated
specifically for Sales-Agent4 (not screenshots of an existing product,
and not loose mood-board inspiration) and provided by the CEO as the
visual foundation of the entire application, all explicitly framed as
explorations of *one* product rather than competing options; the actual,
current state of the repository (`frontend/` and `backend/`, inspected
directly — not assumed); and the real backend data model and state
machines built across M0–M7.4, which this UI will sit on top of and must
be truthful to.

**Governing rule for this revision, stated plainly because it changes
how every decision below is justified:** the concepts are preserved as
closely as possible — layout, visual composition, information hierarchy,
and the premium aesthetic they establish. A concept element is only
changed when there is a clear architectural, usability, scalability, or
technical reason to change it, and every such change is argued
explicitly below, with the replacement held to a higher bar than "looks
fine" — it has to be demonstrably better, not just different. Where the
nine concepts already agree with each other (which is most of what's in
them), that agreement is treated as settled and is not re-litigated by
taste. Where they genuinely disagree, the resolution favors whichever
side the *majority and most-resolved* concepts already converged on —
several of the corrections below are not this document overriding the
concepts, they are this document following a refinement the concepts
had already made among themselves from the earlier renders to the later
ones (see the concept-by-concept accounting in Section 0).

This governing rule also extends past the dashboard: every page in the
system — Discovery, Research, AI Workforce, Companies, Contacts,
Pipeline, Conversations, Outreach, Analytics, Settings, and any future
module — inherits the same visual DNA the dashboard establishes. This is
now a hard requirement, specified concretely per page in Section 9, not
a general aspiration. No page is permitted to default to a generic CRUD
or admin-panel treatment just because its content (a table of contacts,
a settings form) is inherently plainer than a world map. A plain table
of contacts still lives inside the same operating system, and must look
like it.

**Grounding disclosure, read this before anything else:** the existing
frontend (`frontend/src`) is a plain, unstyled Tailwind app — default
`tailwind.config.js` with no theme extension, an `index.css` containing
only the three stock `@tailwind` directives, a light-mode `Sidebar.tsx`
with five flat nav items, and no logo, icon, or brand asset anywhere in
the repository. Twenty pages already exist (`Businesses`, `Contacts`,
`Pipeline`, `Prospects`, `DiscoveryJobs`, `DiscoverySearches`,
`ResearchJobs`, `ProspectResearch`, `ProspectStrategy`,
`ProspectOutreach`, `PersonalizationJobs`, `OutreachPlaybooks`,
`CompanyProducts`, `CompanyICP`, `CompanyKnowledgeBase`,
`CompanyProfileEditor`, `WorkspaceSettingsPage`,
`BusinessEmailSignature`, `Settings`, plus `delivery/`), built purely
functionally, M0 through M6, with zero visual-identity investment. M8 is
therefore not an incremental skin over an existing design system — there
is no existing design system to extend. This document establishes the
first one, and Section 9 includes an explicit reconciliation of every
existing page against the new information architecture, so nothing gets
silently orphaned when implementation eventually happens.

---

## 0. How the nine concepts were read, and what came out of them

The brief was explicit: do not treat the nine images as separate
dashboard ideas to pick a "winner" from. They were read as nine takes on
the same underlying product, and cross-referenced against each other to
find what recurred (signal) versus what varied (noise or unresolved
exploration). This section records that analysis directly, because the
rest of the document makes a lot of decisions that only make sense if
this reasoning is visible rather than asserted.

**What was consistent across all nine, and is therefore treated as
settled product identity, not a choice being made here:**

- A near-black canvas with electric blue/cyan/purple/orange glow accents,
  in every single concept, with no exceptions. This is the palette.
- A world map as the largest, most central element of the dashboard, in
  every concept. This is not being decided in this document — it was
  already decided nine times independently.
- A persistent left sidebar, a top command strip with global search, an
  "AI is active" status indicator, notifications, and a workspace/user
  identity cluster.
- A right-hand contextual intelligence panel tied to whatever is
  selected on the map.
- A live AI agent roster with per-agent current-task text and a status
  indicator.
- A live, timestamped activity feed.
- A recommendations module with specific, confident, actionable copy
  ("Germany shows strong import demand for pharmaceuticals and
  machinery, increase outreach to mid-sized distributors" — not
  "increase your sales").

**Where the concepts disagreed with each other, or repeated themselves
in a way worth correcting — and, for each one, the concept-level
evidence for the resolution, not just a preference:**

1. **Sidebar structure — the one genuine close call, decided on
   usability/scalability grounds.** Concepts 1–4 use one flat list of
   eleven-plus items with no grouping; concepts 5–9 group navigation into
   named zones (AI Workforce / CRM / Intelligence / Settings). This is
   close to an even split (4 versus 5), so it is not resolved by majority
   alone — it's resolved because a flat list of this length has a real,
   demonstrable usability cost (no hierarchy, forces a full scan to find
   anything) that only gets worse as the product adds pages, which the
   brief itself asks this system to be built for ("long-term
   scalability"). **The grouped model (5–9) is kept, formalized in
   Section 3.** This is the only structural decision in this document
   that isn't simply "follow what the concepts already converged on,"
   and it's named as such rather than disguised as consensus.

2. **Redundant KPI rows — the concepts corrected this themselves.**
   Concept 5 repeats nearly the same six metrics twice, verbatim, once
   above the map and again below it. Concept 9 — a later, more resolved
   iteration of the same layout — replaces the second copy with a
   "Today's Summary" card reporting *today's discrete counts* (new
   buyers found, emails sent, replies received, meetings booked), which
   is genuinely different information (today's deltas, not a repeat of
   running totals). **This document keeps concept 9's fix, not concept
   5's duplicate** — this is preserving the concepts' own most-resolved
   direction, not overriding them.

3. **Map rendering strategy — both preserved, neither discarded.**
   Concepts 1, 2, 5, 7, 8, 9 render countries as point markers/hotspots
   connected by arcs; concepts 3 and 4 render the *selected* country as a
   glowing, filled country-shape silhouette. Both are kept exactly as
   drawn, as two states of the same element rather than a choice between
   them: hotspots + arcs are the always-on default (they're what every
   concept but two independently converged on, and they're the only
   treatment that scales to dozens of simultaneously active countries
   without turning into visual mud), and the filled-country glow becomes
   the *selection/focus* state — exactly what concepts 3–4 use it for —
   applied when a country is chosen. Nothing from either concept is cut.

4. **The two horizontal pipeline widgets — kept, as concepts 1–2 already
   show them, distinguished by color rather than restructured.** Concepts
   1 and 2 already label "AI Pipeline" and "Sales Pipeline" as two
   clearly separate, explicitly titled panels — on reflection, an earlier
   draft of this document proposed merging them, on the theory that two
   similar-looking box-rows would read as duplicates. That concern
   doesn't survive contact with the actual concepts: they are already
   distinctly labeled, and merging them would have removed a real,
   deliberately-composed element without a strong enough reason, which
   fails the bar this revision holds every change to. **Corrected
   decision: both widgets are kept, side by side, in their original
   horizontal stage-box form, exactly as concepts 1–2 render them.** The
   only refinement applied is color, not structure: the AI Pipeline
   (Discovery→Research→Qualification→Personalization→Outreach→Reply
   Intelligence) uses `accent-ai` (purple, this system's fixed
   AI-attribution color, Section 4.1) since it is AI operational
   throughput; the Sales Pipeline (Qualified Lead→Meeting→Sample→
   Quotation→Negotiation→Purchase Order→Customer) uses `accent-primary`
   since it's commercial/CRM data. Concepts 5, 6, 7, 8, and 9 additionally
   show a funnel-chart "Pipeline Overview" lower on the dashboard — that
   is a third, distinct visualization (a conversion funnel, not a stage
   list) and is kept too, addressed in item 6 below and Section 8, not
   treated as competing with the two stage-box widgets.

5. **Fabricated progress percentages — narrowly corrected, not removed.**
   Some agent cards (concepts 4, 9) show a numeric completion percentage
   under an agent that's "Researching" or "Reading." Most research/
   writing/thinking tasks don't have a natural notion of "40% done" — a
   percentage there states something false, not just something
   decorative, which is a technical-correctness problem, not a taste
   preference, and squarely meets this revision's bar for changing a
   concept element. The correction is narrow: numeric progress is
   preserved exactly as shown wherever it's real ("42 of 156 companies
   scored," a genuine count), and only replaced with an indeterminate
   state treatment where no real denominator exists. Full rule in
   Section 5.

6. **Bottom-zone dashboard modules — kept close to the majority/most-
   resolved concepts, with the specific minority items relocated to the
   pages the concepts themselves already build for them.** Across the
   nine concepts, candidate bottom-zone modules are: AI Workforce,
   Activity Timeline, Mailbox Brief, Today's Priorities, Pipeline
   Overview (funnel), Top Performing Countries, Market Intelligence,
   AI Recommendations, Email Performance, Recent AI Discoveries, Company
   Research Queue, Scheduled Outreach, Recent Replies, Conversation
   Health. Sorted by how many concepts actually carry each one:
   - **Kept on the dashboard, majority-supported:** AI Workforce (present
     in all nine in some form), Activity Timeline (7 of 9), Mailbox Brief
     (6 of 9), Today's Priorities (6 of 9), AI Recommendations (7 of 9),
     Pipeline Overview funnel (5 of 9 — concepts 5, 6, 7, 8, 9), Top
     Performing Countries (4 of 9 — concepts 5, 6, 7, 8, all among the
     most resolved). **An earlier draft of this document incorrectly cut
     Pipeline Overview and Top Performing Countries from the dashboard —
     that was wrong given how consistently the later concepts carry them,
     and is corrected here and in Section 8.**
   - **Relocated to dedicated pages, minority-only:** Recent AI
     Discoveries, Company Research Queue, Scheduled Outreach, Recent
     Replies, and Conversation Health appear *only* in concepts 3 and 4
     — and concept 6, the single concept that also lays out the full
     dedicated-page catalog, already places this exact content on
     Discovery, Research, Outreach, and Conversations pages respectively,
     not the dashboard. Relocating these five is therefore not this
     document overriding concepts 3–4, it's following concept 6's own,
     more complete answer to where that content belongs.
   - **Reconciled rather than cut:** Market Intelligence's full tabbed
     view (Rankings/Imports/Competitors/Economy) appears only in concept
     2, as a single dense module. Its content isn't discarded — it
     becomes the "deep dive" expansion of the Country Intelligence panel
     (Section 8), which is where a user drilling into trade/economic
     detail for a specific country already goes; the dashboard itself
     keeps the compact "Top Performing Countries" ranking that the
     majority of concepts already show there.
   - **Relocated, true minority:** Email Performance appears only in
     concept 9 and belongs on the Outreach/Analytics page as detail, for
     the same reason.

7. **The persistent bottom quick-action bar — kept, not folded into the
   command palette.** Concepts 5, 6, 7, 8, and 9 — a clear majority,
   including the fullest page-catalog concept — all show a standing
   action bar (New Discovery Search / Generate Research / Create Outreach
   / Mailbox Brief / AI Assistant) at the foot of the dashboard. An
   earlier draft of this document proposed retiring it in favor of the
   command palette alone, on the theory that it duplicated the palette's
   job. On reconsideration that isn't a strong enough reason: a glanceable
   bar of the five most common actions and a keyboard-driven palette for
   everything else are complementary, not redundant — plenty of premium
   tools ship both — and there was no real technical or usability
   conflict forcing a choice. **Corrected decision: the quick-action bar
   is kept exactly as the majority of concepts render it.** The command
   palette (Section 3) remains, positioned explicitly as the
   power-user/keyboard path to the same and additional actions, not a
   replacement for the bar.

8. **Workspace identity shown in two places — kept, re-read as two
   different jobs rather than one duplicated control.** The sidebar
   carries a workspace switcher at its base; the top command strip
   separately shows the current workspace name alongside the user's
   avatar/role. An earlier draft of this document treated the second one
   as a redundant duplicate of the sidebar switcher and proposed removing
   it. On closer inspection that's not accurate: the sidebar control is
   the *interactive switcher* (change workspace), while the top-strip
   element is a *persistent identity confirmation* (which workspace am I
   in, visible without looking down at the sidebar, especially useful
   once a dense dashboard is scrolled). These are different jobs. **Both
   are kept, exactly as shown.**

9. **Inconsistent naming.** "Dashboard" / "AI Sales Command Center" /
   "AI Sales Command Dashboard." The page is titled "Command Center" (the
   stronger, more Mission-Control-appropriate name, and the majority
   choice across the later, more resolved concepts); "sales-agent4 — AI
   Sales Operating System" remains the product-level identity in the
   sidebar header and browser chrome, not the page title.

10. **Three inconsistent brand marks** appear across the nine concepts: a
    faceted diamond/spark gradient icon (concepts 1, 2, 5, 6), a plain
    circular gradient "S" (concepts 7, 8), and a plain initials avatar
    used as if it were the product mark (concept 9, where it's actually
    standing in for the user/workspace avatar, but its visual weight
    competes with the real mark elsewhere). This is not a case of picking
    one concept's idea over another's — a single product cannot ship
    three simultaneous logos regardless of how closely the concepts are
    otherwise preserved, so consolidation to one mark is required, not
    optional. Handled in Section 6.

The rest of this document is that same design language, made consistent
across all nine concepts and extended to cover every page the product
needs — not a transcription of any single concept, but not a departure
from what all nine of them, read together, already establish either.
Ten corrections came out of the analysis above; the other roughly ninety
percent of what's in the concepts — the palette, the map-as-centerpiece,
the KPI strip, the agent roster, the activity feed, the recommendation
cards, the overall density and layout — is carried forward unchanged.

---

## 1. Design Philosophy

**Identity statement.** Sales-Agent4 is not a system of record. Every
screen must read as a live operations surface for a workforce that is
already working, not a filing cabinet waiting to be queried. The test
for every design decision in this document: *does this make the AI's
work more visible, or does it just make the screen busier?* If a design
choice doesn't pass that test, it doesn't belong, no matter how
attractive it looks in isolation — several elements identified in
Section 0 fail this test and were cut for exactly that reason.

**What the reference points actually contribute** (not just mood, but
structural lessons):

- **Bloomberg Terminal** — density with hierarchy. A terminal packs an
  enormous amount of live data onto one screen, but nothing on it is
  ambiguous about what it is or how urgent it is, because typography,
  color, and position do the sorting instead of whitespace alone. This
  license to be dense is *not* a license to be cluttered — Section 8's
  content budget exists specifically to keep this distinction real.
- **Palantir** — the dark operations-center aesthetic and graph/network
  visual grammar (nodes, connections, flows) as the native way to show
  relationships between entities (buyers, countries, agents, deals)
  rather than defaulting to tables for everything.
- **Cursor / Linear** — restraint and speed. Minimal chrome, a
  keyboard-first command palette, snappy micro-interactions, no
  unnecessary modal ceremony. These products feel premium because of
  what they *leave out*, not because of decoration.
- **Mission Control** — glanceable state boards. A flight controller
  doesn't read prose, they read a small number of unambiguous status
  signals from across the room. The AI Workforce roster and the
  activity feed are this project's status board.

**The "already working" feeling is achieved structurally, not
decoratively:** by having a small set of modules that are *always* live
(the map, the workforce roster, the activity feed — see Section 5),
rather than by adding animation to otherwise-static modules. A dashboard
that is mostly static with a few looping decorative flourishes reads as
staged. A dashboard where three or four specific things are visibly,
continuously true reads as real.

**Explainability is a design value, not just a backend property.** M7's
Supervisor layer was built so that every `SupervisorDecision` carries a
required, non-optional `reason`, and every agent invocation records
`inputs_consumed`. That was an architectural decision made specifically
so "why did the AI do this" is always answerable. The UI has an
obligation to actually surface that — an AI Recommendation card that
just says "Follow up with 7 prospects" wastes data the backend goes out
of its way to produce. Every AI-attributed statement in this UI should
be able to answer "why" in one click, because the backend can already
answer it.

---

## 2. Information Architecture

Four top-level zones, replacing the flat list currently in
`Sidebar.tsx` and unifying the grouped pattern that the stronger concepts
(5–9) converged on independently:

| Zone | Contains | Answers |
|---|---|---|
| **Command Center** | The dashboard itself (single item, no sub-nav) | "What deserves my attention right now?" |
| **AI Workforce** | AI Agents (roster + trace), Discovery, Research, Outreach, Mailbox Brief, Follow-ups | "What is the AI doing, and what has it found?" |
| **CRM** | Companies, Contacts, Pipeline, Deals, Products | "What is the state of my actual business relationships?" |
| **Intelligence** | Conversations, Analytics, Reports, Country Intelligence (deep view) | "What has been learned, and how is it performing?" |

Settings (workspace, users, billing, integrations, ICP, knowledge base,
brand email signature) sits below the four zones as a fifth, visually
de-emphasized group, matching the existing pattern where Settings is
already separated from primary navigation.

This is not a cosmetic regrouping. It maps directly onto how the backend
itself is organized, which is exactly why it holds up under scrutiny
rather than being an arbitrary UX preference:

| IA zone/page | Backend milestone(s) it surfaces |
|---|---|
| AI Agents (roster + trace) | M7.2 Agent Runtime, M7.3 Supervisor, M7.4 Supervisor Invocation |
| Discovery | M1 Buyer Discovery Engine |
| Research | M2 AI Research & Prospect Intelligence |
| Outreach | M3 Personalization Engine + M5 Outreach Delivery Engine |
| Mailbox Brief | M5 Delivery (mailbox activity) + M6 Reply Intelligence |
| Conversations | M6.1–M6.4 (Conversation, EmailMessage threading, reply classification) |
| Pipeline / Deals | M4 (Pipeline stage model) |
| Companies / Contacts / Products | M0/M1/M4 core CRM entities |
| Country Intelligence | M1 Discovery geography + M2 Research market data, presented as a cross-cutting lens, not a new backend module |

No IA node in this document invents a page for a capability the backend
doesn't have. Where a concept implied something the backend can't yet
back (see Section 14 — most notably "Paused" agent state and true
real-time push), that's called out explicitly rather than quietly
designed around.

**Existing-page reconciliation** (so this document is checkable against
the real repo, not just a fresh proposal floating above it):

| Existing page | New IA home |
|---|---|
| `Prospects.tsx`, `Pipeline.tsx` | CRM → Pipeline / Deals |
| `Contacts.tsx` | CRM → Contacts |
| `Businesses.tsx`, `CompanyProfileEditor.tsx` | CRM → Companies |
| `CompanyProducts.tsx` | CRM → Products |
| `CompanyICP.tsx`, `CompanyKnowledgeBase.tsx` | Settings (workspace-level configuration, not daily-use CRM) |
| `DiscoverySearches.tsx`, `DiscoveryJobs.tsx` | AI Workforce → Discovery |
| `ResearchJobs.tsx`, `ProspectResearch.tsx` | AI Workforce → Research |
| `ProspectStrategy.tsx`, `PersonalizationJobs.tsx`, `ProspectOutreach.tsx`, `OutreachPlaybooks.tsx` | AI Workforce → Outreach |
| `BusinessEmailSignature.tsx` | Settings |
| `delivery/*` | AI Workforce → Mailbox Brief / Settings (provider connections) |
| `WorkspaceSettingsPage.tsx`, `Settings.tsx` | Settings |
| `Login.tsx`, `OAuthCallback.tsx` | Unchanged, restyled only |

Nothing here is a page-count reduction — it's a re-grouping. Actually
migrating routes is implementation and is out of scope for this
document (Section 14).

---

## 3. Navigation Architecture

**Primary sidebar.** Persistent, grouped by the four zones above, each
zone header collapsible. Product mark + wordmark at the top (Section 6),
workspace switcher directly below it (the existing `CompanySwitcher`
component's role is preserved, just restyled), user identity + sign-out
pinned to the bottom — this structure already exists in
`Sidebar.tsx` today and is kept, not reinvented. Active-item state uses
a left accent bar + filled icon, not the current solid-block highlight,
because a solid block reads as heavier than a five-hour-a-day tool
should feel. Collapses to an icon-only rail below the tablet breakpoint
(Section 7).

**Top command strip**, left to right: global search / command palette
trigger, then (right-aligned) an "AI System — Active" status pill
(live, reflects whether any Supervisor/Agent execution is currently
running — a real signal, not a static label), notification bell,
date/time, and the workspace name + user avatar/role cluster. This
cluster is a **persistent identity confirmation** — which workspace you
are in and who you are, visible without looking at the sidebar,
especially once a dense dashboard is scrolled — and is a different job
from the sidebar's workspace *switcher* at its base (Section 0 item 8).
Both are kept, exactly as the concepts show them; neither is a duplicate
of the other.

**Command palette (⌘K).** Keyboard-first, in the Cursor/Linear
tradition. Scope: page navigation, entity search (companies, contacts,
prospects, conversations), and the same *actions* the dashboard's
persistent quick-action bar exposes, plus more. This is the power-user,
keyboard-driven path to those actions — it complements the quick-action
bar (below), it does not replace it; a glanceable bar of the five most
common actions and a keyboard palette for everything else are two
different jobs, not one duplicated.

**Persistent quick-action bar (dashboard footer).** New Discovery
Search, Generate Research, Create Outreach, Open Mailbox Brief, AI
Assistant — kept exactly as the majority of concepts (5, 6, 7, 8, 9)
render it, always visible at the foot of the Command Center dashboard.

**Breadcrumbs.** Already exist (`Breadcrumbs.tsx`) and are kept —
restyled for the dark system, not replaced. They remain the correct
answer for "where am I" on deep pages (e.g. a specific company inside
Research), which a sidebar alone can't express.

**In-page secondary navigation.** Tabs, used for the recurring
overview-plus-detail page template (Section 9) — Overview / Financials /
Products / Contacts / Imports / News / AI Summary, as concept 6's
Research page demonstrates. Tabs are a page-local pattern, never a
substitute for sidebar-level IA.

---

## 4. Design System

### 4.1 Color

A dark canvas is not "black" — pure black kills the glow effects that
carry most of the liveness in this system, and it's what several of the
weaker concept renders actually do wrong. The canvas uses a deep
blue-black (roughly `#0A0E17`–`#0B0F1A` range), never true `#000000`,
so glows and accent colors have somewhere to bloom into.

| Token | Role |
|---|---|
| `surface-0` | Canvas / page background |
| `surface-1` | Card/panel background (one step lighter than canvas) |
| `surface-2` | Nested/elevated content within a card (e.g. a table row on hover) |
| `border-hairline` | 1px, low-opacity white, the only border weight in the system |
| `accent-primary` (electric blue) | Primary actions, active nav, default map hotspots |
| `accent-secondary` (cyan) | Secondary data series, links |
| `accent-ai` (purple/violet) | Anything specifically AI-attributed — agent cards, AI Recommendation copy, the Supervisor/Agent trace. This is a **semantic** color, not a decorative one: purple always means "the AI produced or is producing this," everywhere in the product. |
| `status-success` (green) | Completed, positive deltas, won deals |
| `status-warning` (amber) | Waiting, medium-impact priorities, needs-attention |
| `status-danger` (red) | Failed, high-impact/urgent, negative deltas |
| `status-info` (blue-cyan) | Running/in-progress, neutral live state |

Deriving the palette from the brand mark's own gradient (Section 6)
rather than picking accent colors independently is what makes the whole
system look designed rather than assembled — this is the resolution of
Section 0 item 8.

**A rule that directly corrects a real weakness observed across several
concepts:** glow is semantic, not default. Glow means "this element is
live or currently AI-touched right now." A KPI card that isn't actively
updating does not get a glowing border just because it looks nice — some
concepts glow every card border simultaneously, which cheapens the
signal until it means nothing. Reserve it and it stays meaningful.

### 4.2 Typography

A geometric/technical sans (Inter or equivalent) for all UI text.
Numeric data — KPI values, table figures, timestamps, percentages — uses
tabular/lining figures throughout, so columns of numbers align and
update without re-flowing digits, and so the numeric display has the
"terminal" precision the Bloomberg reference point is about. This is a
concrete, checkable rule, not just an aesthetic preference: any
component rendering a number is required to use the tabular-numeral
style.

Scale: a restrained 6–7 step type scale (display, h1–h3, body, caption,
micro-label), reused everywhere rather than each module inventing its
own sizes — the current absence of *any* type scale in the codebase
(plain default Tailwind) makes this the single highest-leverage token to
land first in implementation.

### 4.3 Spacing & grid

8pt base spacing unit. 12-column responsive grid at desktop, collapsing
per Section 7. Card padding, gap, and radius are each a single token
reused everywhere (no bespoke per-card spacing) — this is what makes
nine independently-designed concepts able to become one product instead
of nine products stitched together.

### 4.4 Elevation

Because the canvas is dark, elevation is communicated by *lightness +
border + optional glow*, not by drop shadow — a drop shadow barely
registers against a near-black background, which is a real, checkable
rendering fact, not a style preference. Four levels: canvas → resting
card → hovered/focused card → floating (modal, command palette,
dropdown), each one step lighter and with a slightly stronger hairline
border than the last.

### 4.5 Glass

Used sparingly and specifically for **overlays that sit above other
content** — the command palette, modals, dropdown menus, toast
notifications. Not applied to standing dashboard cards. Several concepts
apply a translucent/frosted treatment to nearly every panel
simultaneously; stacked across a dense dashboard, that reduces contrast
and makes text harder to read exactly where readability matters most.
Glass is a z-axis cue ("this is floating above the page"), not a
finish applied everywhere for texture.

### 4.6 Component catalog (purpose + states, not implementation)

- **Buttons** — primary (filled, accent-primary), secondary (hairline
  border, transparent fill), ghost (text-only), destructive (danger).
  States: default, hover, active, focus-visible, disabled, loading
  (spinner replaces label, button width does not jump).
- **Inputs / dropdowns / multi-select** — dark-surface fields, hairline
  border, accent-primary focus ring (2px, offset, always visible —
  see Section 12; several concepts show no focus state at all, a real
  gap this system does not repeat).
- **Tables** — dense by default (Bloomberg-influenced), row hover =
  `surface-2`, sortable column headers, sticky header on scroll,
  status/badge cells use the semantic status colors from 4.1.
- **Charts** — line (trend), funnel (conversion, replacing the old
  "pipeline as boxes" pattern per Section 0 item 4), horizontal bar
  (ranked lists — top countries, top industries), donut (composition —
  mailbox brief). One charting approach reused everywhere, never a
  different chart library's default look per module.
- **Maps** — the World Map module (Section 8) and its Country Intelligence
  companion (Section 8/10) are specified together since neither makes
  sense alone.
- **Timelines** — the Activity Timeline pattern: icon, actor (agent
  name), action text, relative timestamp, live-updating at the top.
- **Notifications** — toast (transient, bottom-right) for user-triggered
  action feedback; the notification bell's dropdown (persistent list)
  for AI-originated events (a new opportunity found, a reply received).
  These are deliberately different surfaces because they have different
  urgency and lifespans.
- **Status indicators** — a small fixed vocabulary reused everywhere: a
  colored dot + label. Never color alone (Section 12).
- **Badges / tags** — impact level (High/Medium/Low), pipeline stage,
  country flag + name, agent type.
- **AI cards / Agent cards / Country cards / Recommendation cards** —
  specified in Section 10 as composed components, since they recur
  across the dashboard *and* dedicated pages and must be built once,
  not per-page.
- **Loading / empty / error states, skeleton loaders** — every module
  that fetches data defines all four, not just the happy path; empty
  states are branded (Section 6), not a bare "No data" string.
- **Hover / focus states** — defined once per component tier, inherited,
  not redefined per instance.

---

## 5. Motion System

Motion is categorized by *why* it's happening, matching the brief's own
framing exactly, plus a fourth category the brief implies but doesn't
name — things that should specifically **not** animate.

| Category | Examples | Behavior |
|---|---|---|
| **Always alive** | World map hotspot pulses and arc flow, AI Workforce roster status dots, Activity Timeline's live-append, the "AI System — Active" pill | Slow, continuous, low-amplitude. This is ambient truth, not a show — see the calibration note below. |
| **Animate on change** | KPI numbers (count up/down to new value), chart redraw, pipeline/funnel stage movement, a new AI Recommendation appearing, agent status transitioning (Idle→Researching→Writing→Completed) | Triggered strictly by a real state change from the backend. Duration proportional to significance: a KPI tick is ~200ms, an agent state transition is ~300–400ms with a brief highlight flash so it's noticeable against the calm baseline. |
| **Animate on interaction** | Button press, card hover/lift, table row expand, dropdown/menu open, panel slide-in (Country Intelligence drawer) | Fast, 120–200ms, standard easing. This is feedback, not storytelling — it should feel instant. |
| **Never animate / static by design** | KPI card borders (unless that specific card is mid-update), any element with no underlying state change, decorative loops with no data behind them | If nothing changed, nothing moves. This is the direct fix for Section 0 item 5 (fake progress) and the broader "motion for decoration" risk the brief itself warns about. |

**Calibration note, because this is where "alive" and "distracting" are
easy to confuse over an eight-hour workday:** ambient motion (map pulse,
status dots) must be slow and low-contrast enough to recede into
peripheral awareness — it's there so a glance confirms "yes, still
running," not so it competes for foreground attention. State-change
animation is allowed to be sharper and more noticeable *specifically
because* it's rare and contrasts against a calm baseline. If everything
moves at the same intensity, nothing reads as more important than
anything else, which is the opposite of what a Mission Control interface
is for.

**Real-data-driven triggers — how animation stays honest.** Every
category-2 animation above must be traceable to an actual backend event,
not a client-side timer pretending to be one:

| UI motion | Backend fact that must drive it |
|---|---|
| Agent card: Idle → Running | A `SupervisorDecision` of kind `RUN_AGENTS` naming that agent, or `AgentRuntime` beginning execution |
| Agent card: → Completed / Failed | `AgentOutcome.SUCCESS` / `AgentOutcome.FAILURE` from that agent's `AgentExecutionResult` |
| Agent/workflow card: → Waiting | `WorkflowInstanceStatus.WAITING` (a `SupervisorDecision.WAIT`, post-M7.4-correction, or the engine's own `engine.wait_for_event`) |
| Activity Timeline new row | A new `WorkflowStepInvocation` / `SupervisionStep` being recorded |
| World map hotspot intensity | Real Discovery/Research volume for that country, not a decorative random pulse |

This table is the enforcement mechanism for "animation must never exist
purely for decoration": if a proposed animation can't be mapped to a row
in a table like this during implementation, it doesn't ship.

**A named UI-facing state vocabulary, and an explicit disclosure about
where it does and doesn't yet have backend support.** The brief asks for
agents to visibly move through Idle, Thinking, Researching, Reading,
Writing, Scoring, Waiting, Reviewing, Running, Completed, Paused, Failed.
The backend does not need twelve new enum values to support this — it
already has exactly the right primitives (`AgentOutcome`, `ActionOutcome`,
`WorkflowInstanceStatus`, `DecisionKind`), and the extra specificity
(*"Researching"* vs. just *"Running"*) comes from **which agent** is
executing and **which action** it's running, resolved by a presentation-
layer mapping, not a backend change:

- `Idle` — agent registered, no current invocation.
- `Thinking` — a Supervisor's `decide_next()` is being evaluated
  (Supervisor-level, precedes any specific agent's turn).
- `Researching` / `Reading` / `Writing` / `Scoring` — all map to
  `AgentRuntime` mid-execution (no distinct backend state); the specific
  verb is chosen from the agent's own identity (a Research agent
  "Researches," an Outreach agent "Writes," a Qualification-style agent
  "Scores"). This mapping table is implementation detail, but the
  *rule* — that verb choice is presentation, not a backend field —
  belongs here so nobody tries to add twelve new enum values later.
- `Waiting` — `WorkflowInstanceStatus.WAITING` / `ActionOutcome.PENDING`.
  Maps directly and exactly, no interpretation needed.
- `Reviewing` — a human-approval `WAIT` (`ResumeTriggerType.HUMAN_APPROVAL`).
- `Running` — generic fallback label when no more specific verb applies.
- `Completed` — `AgentOutcome.SUCCESS` / `DecisionKind.COMPLETE`.
- `Failed` — `AgentOutcome.FAILURE` / `DecisionKind.FAIL` or `ABORT`.
- **`Paused` — has no backend equivalent today.** There is currently no
  API to pause a running `WorkflowInstance`; `RUNNING`/`WAITING` are the
  only non-terminal states the engine has. Showing a "Paused" control in
  the UI without backend support to back it would be exactly the kind of
  decorative-but-false signal this whole document argues against.
  Recorded as a deferred backend capability in Section 14, not silently
  designed around.

---

## 6. Branding System

**Logo.** None of the nine concepts is a finished, final asset — three
different marks appear (a faceted diamond/spark gradient icon; a plain
circular gradient "S"; an initials avatar that isn't actually the
product mark but visually competes with one). A repository-wide search
confirms there is no logo, favicon, or icon asset checked in anywhere
today. **Recommendation:** converge on the faceted diamond/spark
gradient direction — it's the one used in the most-resolved concepts
(1, 2, 5, 6) and it reads distinctly at both large (splash/login) and
small (favicon, 16px sidebar) sizes, which a typographic "S" mark
struggles with at favicon size. **This is a recommendation, not a
finished asset** — a real production logo file (SVG, multiple weights,
a monochrome/reversed variant for dark and light contexts, and a
favicon-specific simplified version) does not exist yet and is explicit,
named deferred work (Section 14), not something this document can
resolve on its own.

**Palette derivation.** The blue→purple/cyan gradient used in the
recommended mark is the literal source of `accent-primary`,
`accent-secondary`, and `accent-ai` in Section 4.1 — the palette is
built around the logo, per the brief's explicit requirement, not
picked independently and then coincidentally similar to it.

**Branded surfaces**, each specified at the level this document deals
in (purpose and content, not pixels):

- **Splash/loading screen** — mark animates in (a single, restrained
  reveal, not a decorative loop — consistent with Section 5's "loading
  states are the one place a loop is earned, because it's communicating
  real wait time"), tagline "AI Sales Operating System."
- **Login** — dark canvas, mark + product name, no world-map decoration
  competing with the actual task (signing in); the map is this
  product's identity *inside* the tool, not wallpaper on the door.
- **Favicon** — simplified single-color mark, legible at 16px.
- **Empty states** — every empty state (no discoveries yet, no
  conversations yet, no companies yet) uses the mark plus a
  situation-specific illustration treatment (an idle, not-yet-scanning
  version of the world map motif, for instance, for an empty Discovery
  page) and a specific next action, never a generic "No data" string.
- **Onboarding** — first-run flow introduces the map and the AI
  Workforce roster as the two identity anchors before anything else,
  matching Section 1's "the AI is already working" objective from the
  very first screen a new user sees.
- **AI visuals** — every AI-attributed surface (recommendation cards,
  agent cards, the Supervisor trace) uses `accent-ai` (purple/violet)
  consistently, so a user learns, system-wide, that "purple means the
  AI made this," which is the actual mechanism by which the interface
  becomes "as recognizable as Stripe/Linear/Cursor" — a single
  consistently-applied semantic color read across dozens of screens,
  not a one-off hero visual.

**Voice.** AI-attributed copy is specific and confident, following the
pattern already present in the strongest concepts — "Germany shows
strong import demand for pharmaceuticals and machinery, increase
outreach to mid-sized distributors," not "You have new
recommendations." Specificity is itself a trust signal; vague copy
undermines the "confidence" design principle regardless of how the
pixels around it look.

---

## 7. Responsive Strategy

The brief's own three-device framing (Desktop Command Center / Tablet
Executive Workspace / Mobile Executive Companion) is adopted as the
*naming* for three usage contexts — but it is explicitly **not** read as
"build three separate UIs," which is how concept 1 visually presents it
(three distinct mockups side by side). That reading would directly
contradict the brief's own later requirement: "all platforms should feel
like the same operating system, not three separate products." **One
responsive system, three density tiers, the same components
throughout.**

| Tier | Breakpoint | What changes |
|---|---|---|
| Desktop — Command Center | ≥1280px | Full sidebar (expanded), full dashboard grid (map + intelligence panel + full bottom-zone modules per Section 8) |
| Tablet — Executive Workspace | 768–1279px | Sidebar collapses to icon rail (expandable on demand); dashboard becomes single-column stacked, map remains the largest element but the Country Intelligence panel moves below it instead of beside it; bottom-zone modules become a 2-column grid instead of 4 |
| Mobile — Executive Companion | <768px | Sidebar becomes a bottom tab bar (4 primary zones + "more"); dashboard becomes a fully vertical, prioritized stack — KPI strip becomes a horizontal-scroll strip, map is present but reduced to a glanceable summary state with a "View Full Map" expand, detail pages favor single-column card stacks over tables |

Every tier renders from the *same* component set (Section 10) with
responsive props, not tier-specific component variants — this is what
actually delivers "same operating system" rather than three products
that happen to share a color palette.

---

## 8. Dashboard Architecture

**The governing rule, restated as an enforceable budget, not just a
sentiment:** the dashboard answers "what deserves my attention right
now." Anything that answers a different question ("what happened over
the last quarter," "show me every deal") belongs on a dedicated page.
This section is where Section 0's sprawl finding gets resolved into an
actual cut list.

**Three vertical zones, in order:**

**Zone 1 — Command Strip.** One KPI row (Active Buyers, AI Tasks
Running, Open Conversations, Opportunities, Revenue Pipeline, AI
Confidence Score), each with a sparkline and delta. Today's Summary card
(today's discrete counts) sits at the end of this strip, not duplicated
as a second KPI row (Section 0 item 2).

**Zone 2 — Global Command Deck.** The World Map (largest single element
on the page, per the brief's explicit requirement) with its Country
Intelligence companion panel to the right. Directly below the map, kept
exactly as concepts 1–2 render them, side by side and distinctly
labeled: the **AI Pipeline** widget (Discovery→Research→Qualification→
Personalization→Outreach→Reply Intelligence, `accent-ai` color) and the
**Sales Pipeline** widget (Qualified Lead→Meeting→Sample→Quotation→
Negotiation→Purchase Order→Customer, `accent-primary` color) — see
Section 0 item 4 for why an earlier draft's proposal to merge these was
wrong and has been reversed.

**Zone 3 — Attention Deck.** The modules the majority of concepts carry
here, each answering a distinct question, no overlap:
- **Today's Priorities** — the ranked, impact-tagged action list.
- **Mailbox Brief** — the donut/summary card (needs-reply, waiting,
  follow-up counts), a shortcut into Conversations, not a full inbox
  rendered on the dashboard.
- **AI Recommendations** — the specific, reasoned suggestions (Section
  1's explainability requirement applies directly here: each
  recommendation card must link to the `SupervisorDecision.reason` /
  agent trace that produced it).
- **Pipeline Overview (funnel chart)** — Discovered→Researched→Outreach→
  Replied→Negotiation→Won, the top-of-funnel conversion view, distinct
  from (and a complement to, not a duplicate of) the Sales Pipeline
  stage-box widget in Zone 2: the stage-box widget shows current count
  *per stage*, the funnel shows the *conversion rate* across the whole
  journey. Kept because 5 of 9 concepts (5, 6, 7, 8, 9) carry it, an
  earlier draft of this document incorrectly cut it — corrected here.
- **Top Performing Countries** — the compact ranked list (flag, name,
  buyer count, growth). Kept because concepts 5, 6, 7, and 8 all carry
  it as a standing dashboard module — an earlier draft incorrectly cut
  this too; corrected here. Distinct from the Country Intelligence
  panel in Zone 2, which is about one *selected* country in depth, not a
  ranked list across many.
- **Activity Timeline** — the live, timestamped feed (present in 7 of 9
  concepts).

**Relocated to dedicated pages — true minority items, following the
concepts' own more complete answer, not overriding it (see Section 0
item 6 for the full accounting):** Recent AI Discoveries, Company
Research Queue, Scheduled Outreach, Recent Replies, and Conversation
Health appear only in concepts 3–4, and concept 6's own dedicated-page
catalog already places this exact content on Discovery, Research,
Outreach, and Conversations respectively. Email Performance (concept 9
only) belongs on Outreach/Analytics detail for the same reason. Market
Intelligence's full tabbed view (concept 2 only) becomes the Country
Intelligence panel's "deep dive" expansion rather than a separate
dashboard module, since that's the more complete answer concept 2's own
sibling concepts already converged toward.

**Country Intelligence, specified as the reusable module the brief asks
for.** Content is tiered so it doesn't try to fit an overwhelming amount
into a narrow column without scrolling, which is a real legibility risk
in the denser concepts:
- **Always visible:** flag, country name, local time, business-hours
  status, opportunity-tier badge.
- **Primary metrics (visible, no scroll):** active buyers, qualified
  prospects, open campaigns — three numbers, not eight.
- **Secondary (scrollable within the panel):** industry breakdown, top
  companies, agents currently active in that country, market-trend
  chart.
- **Deep dive:** an "Expand" action opens a full drawer/page view with
  everything above, plus trade insights and economic indicators, plus
  concept 2's tabbed Market Intelligence detail (Rankings / Imports /
  Competitors / Economy) — folded in here rather than kept as a separate
  dashboard module, per Section 0 item 6 and Section 8's module list.
  This is also the same module reused on Discovery and Research pages
  (Section 10), so it's built once and gains full-page real estate there
  where the dashboard's narrow column doesn't need to be its only home.

---

## 9. Page Architecture

**A single reusable page template**, rather than each page inventing its
own layout, following the strongest pattern in the concepts (the
Research page's Overview/Financials/Products/Contacts/Imports/News/AI
Summary tab structure):

**Template: List → Detail.**
- **List view:** filterable/sortable table or card grid (Discovery
  buyer results, Companies, Contacts, Conversations), an AI-scored
  column where relevant (match score, confidence), bulk actions.
- **Detail view:** header (identity + key stat + primary action),
  tabbed body (Overview always first, then domain-specific tabs), a
  persistent right-hand **AI Insight rail** — this is the same
  structural slot the dashboard's Country Intelligence panel occupies,
  reused as a pattern: whatever page you're on, AI-attributed context
  about the thing you're looking at lives in the same right-hand
  position.

**Page catalog** (zone from Section 2, backend milestone from Section 2,
template from above):

| Page | Zone | Template |
|---|---|---|
| Discovery | AI Workforce | List (buyer search results, filters, AI match score) |
| Research | AI Workforce | Detail (company profile: Overview/Financials/Products/Contacts/Imports/News/AI Summary, Key Contacts, AI Insight rail) |
| Outreach | AI Workforce | List → Detail (prospect list, selecting one opens composer + personalization panel) |
| Mailbox Brief | AI Workforce | Purpose-built summary page (not List/Detail — this is the one page that's fundamentally a triage surface, matching concept 6's page 05) |
| AI Agents | AI Workforce | Purpose-built (grid of agent cards + per-agent execution trace — the visual home of the Supervisor/Agent Runtime explainability data) |
| Conversations | Intelligence | Purpose-built (inbox-style: thread list + message view + AI Analysis rail: intent/sentiment/buying-stage/confidence, directly surfacing M6.4's classification output) |
| Companies / Contacts | CRM | List → Detail |
| Pipeline / Deals | CRM | Purpose-built (kanban-by-stage, per concept 6 page 07, plus the funnel chart from Section 4.6 as a secondary view) |
| Products | CRM | List → Detail |
| Analytics | Intelligence | Purpose-built (charts + rankings, the home for everything cut from the dashboard in Section 8) |
| Reports | Intelligence | List → Detail |
| Settings | Settings | Form-based, grouped by concern (matches concept 6 page 10) |

### 9.1 Visual DNA inheritance — a hard requirement, not an aspiration

The dashboard establishes the product's visual identity. Every other
page is a natural extension of it, not a separate, plainer application
that happens to share a sidebar. This is now a concrete, checkable
requirement: **no page may ship without explicitly accounting for each
row below**, and a page that reverts to a generic light-admin-panel
treatment because its underlying data is plain (a settings form, a
contacts table) has failed this requirement, not found a reasonable
exception to it.

| DNA element | What "inheriting it" means, concretely |
|---|---|
| **Layout philosophy** | Same canvas (`surface-0`), same card-based composition, same 8pt grid and spacing tokens (Section 4.3) on every page — a Contacts list uses the same card/table shell as the dashboard's own modules, not a different admin-template shell. |
| **Card design** | Every card on every page — a contact row, a settings section, a company profile summary — uses the same elevation, radius, border, and (where genuinely live/AI-touched) glow rules as a dashboard card (Section 4.4–4.5). |
| **Typography** | The same type scale and tabular-numeral rule for data (Section 4.2) applies to a Pipeline deal value exactly as it applies to a dashboard KPI. |
| **Color** | The full semantic palette (Section 4.1) — `accent-ai` (purple) for anything AI-attributed, `accent-primary`/`accent-secondary` for the rest, the fixed status-color vocabulary — is used identically everywhere; a Conversations page's AI-detected sentiment badge uses the same purple an Agent card does, not a page-local color choice. |
| **Motion** | Every page follows Section 5's rules: state changes animate, decoration doesn't. A Discovery results table gets a live "new match found" row-insert animation because that's a real event, the same way the dashboard's Activity Timeline does. |
| **Navigation** | The same grouped sidebar, top command strip, and command palette on every page — never a page-specific nav shell. |
| **Component library** | Pages compose from the same tier-2/tier-3 components as the dashboard (Section 10) — a `CountryCard` on Discovery is the *same component* as the one in the dashboard's Country Intelligence panel, not a lookalike rebuild. |
| **AI visual language** | Any AI-produced or AI-scored content — a match score, a recommendation, a classified intent/sentiment badge — is visually marked as AI-attributed (purple accent, and where relevant an agent-avatar/icon), on every page, exactly as the dashboard's Recommendation cards are. This is what makes the AI Workforce feel like it's working *everywhere in the product*, not just on one showcase screen. |
| **World-map-inspired styling** | Country/geography data recurs outside the dashboard (a buyer's country on Discovery, a company's headquarters on Research, a deal's region on Pipeline) and is rendered with the same flag+glow treatment the map and Country Intelligence panel establish — small inline map/globe iconography where a page references geography, not a plain text country name. |
| **Branding** | The mark, wordmark, and loading/empty states (Section 6) are consistent on every page — an empty Contacts list uses the same branded-empty-state pattern as an empty Discovery results page. |
| **Premium spacing** | No page is allowed denser or sparser spacing than the tokens define just because it "is only a settings page" — Settings gets the same premium spacing budget as the Command Center. |
| **Glass/glow rules** | Section 4.5's rule (glass for overlays only, glow reserved for live/active elements) applies uniformly — a page-level modal uses the same glass treatment the command palette does. |
| **Status indicators** | The same dot+icon+label vocabulary (Section 4.6/12) for every status on every page — a Pipeline deal's stage indicator and a dashboard agent's status indicator are drawn from the same component, not two different badge styles. |

**Pages most at risk of defaulting to a generic CRUD treatment, and how
each specifically avoids it:**

- **Companies / Contacts.** The most plain-data-shaped pages in the
  system, and exactly where the temptation to fall back to a stock admin
  table is strongest. Concretely: table rows use the dark
  surface/hairline-border treatment (never a white admin-grid), any
  AI-enriched field (a company's AI-assessed risk level, a contact's
  engagement score) is purple-badged exactly like a dashboard AI
  Recommendation, and a company row's country renders with the same
  flag+glow chip the map's Country Intelligence panel uses — a user
  should be able to tell, from the Contacts page alone with no sidebar
  visible, that they're inside Sales-Agent4 and not a generic CRM.
- **Settings.** Form-heavy by nature, but forms use the same dark-surface
  input/dropdown components as everywhere else (Section 4.6), grouped in
  the same card shells, with the same premium spacing — a settings page
  is allowed to be *calmer* (less live motion, since there's little to
  animate) but never *plainer* in its surfaces, type, or spacing.
- **Pipeline / Deals.** Kanban columns and deal cards use the same card
  elevation/glow rules and status-color vocabulary as an Agent card;
  a deal that an AI agent (e.g. Outreach or Reply Intelligence) recently
  touched carries the same purple AI-attribution marker a dashboard
  Recommendation would.
- **Analytics / Reports.** The chart types defined in Section 4.6 (funnel,
  line, bar, donut) are reused here at larger scale, not swapped for a
  different charting look because this page is "for deep data" — Section
  8's cut list explicitly routes deeper versions of dashboard content
  *here*, specifically so this page still looks like the same product
  the dashboard's lighter versions came from.

Any future module added to the product is evaluated against this table
before it ships — this list is the enforcement mechanism for "every page
should feel premium, consistent, and part of one cohesive product," not
a restatement of the sentiment.

---

## 10. Component Architecture

Four tiers, so the system scales by composition rather than by every new
page inventing new components:

1. **Primitives** — Button, Input, Select, Checkbox, Badge, Tag, Avatar,
   Tooltip, Modal, Toast. No domain knowledge.
2. **Composed components** — `KpiCard`, `AgentCard`, `CountryCard`,
   `RecommendationCard`, `StatusIndicator`, `ActivityFeedItem`,
   `PriorityListItem`. Domain-aware, built once from primitives, reused
   everywhere they appear across dashboard and pages alike (this is the
   direct mechanism by which `CountryCard`, for instance, is *the same
   component* on the dashboard, on Discovery, and on Research — not
   three lookalike implementations).
3. **Modules** — `WorldMap`, `CountryIntelligencePanel`, `AIWorkforceRoster`,
   `ActivityTimeline`, `MailboxBriefSummary`, `CommandPalette`. Each
   composed of tier-2 components plus its own data-fetching/live-update
   logic.
4. **Page templates** — `ListDetailPage`, `DashboardPage`,
   `TriagePage` (Mailbox Brief), `KanbanPage` (Pipeline) — the shells
   from Section 9, into which modules and composed components are
   assembled per page.

**Agent card, specified concretely since it's the component that carries
the most identity-critical weight in this system:** avatar/icon + agent
name + current status (Section 5's vocabulary) + current task text +
elapsed time + (only where genuinely quantifiable) a numeric progress
value. Same component in the dashboard's AI Workforce strip (compact
variant) and the full AI Agents page (expanded variant, with the
execution trace below it) — one component, two density variants, not
two components.

**Extensibility rule.** New agent types, new pipeline stages, new
country entries must be addable via configuration/data (an icon+color
lookup table, matching the backend's own `AGENT_REGISTRY` /
`SUPERVISOR_REGISTRY` extensibility pattern) rather than by writing a new
component per addition. This is what keeps the design system's growth
rate slower than the backend's own agent catalog growth rate.

---

## 11. Animation Philosophy

Restating Section 5's mechanics as the governing principle they serve,
because the "why" needs to survive independently of the specific
duration/easing numbers, which will get tuned during implementation:

**Every animation must be traceable to one of three legitimate sources:
a real state change, a user's direct interaction, or genuine
indeterminate wait time. If it isn't, it doesn't ship.** This single
rule resolves every weak decision identified in Section 0 that involved
motion:

- A fake progress percentage on an indeterminate task fails this test —
  cut, replaced with the pulse-state treatment.
- A decorative looping animation on a static KPI card fails this test —
  cut.
- A slow ambient pulse on the world map, driven by real Discovery
  volume, passes — it's a real state change, just a continuous one.
- A card lift on hover passes — direct interaction.
- A skeleton shimmer while a page's real data is in flight passes —
  genuine wait time, and it stops the instant real content arrives, it
  does not keep looping past that point.

`prefers-reduced-motion` is respected system-wide: every category-1
("always alive") animation gets a static equivalent (a solid indicator
instead of a pulse, an already-drawn map instead of an animated
scan-in) that conveys the same state without motion — this is covered
again, as an accessibility requirement rather than a preference, in
Section 12.

---

## 12. Accessibility Strategy

This is treated as a real constraint this specific aesthetic direction
makes *harder*, not a checklist appended at the end — dark themes with
glow and glass effects are genuinely more prone to contrast failures
than a plain light UI, and none of the nine concepts show a visible
keyboard-focus state anywhere, which is a real, checkable gap this
document does not repeat.

- **Contrast.** All body text against `surface-0`/`surface-1` must meet
  WCAG AA (4.5:1) at minimum; this is tested against the *actual*
  rendered surface color including any glass/opacity effects stacked on
  top of it, not against the nominal token value in isolation — a
  frosted panel over a busy map background is exactly the kind of
  combination that can silently fail contrast even when each layer
  individually looks fine.
- **Color is never the only signal.** Every status indicator (Section
  4.6) pairs its color with an icon and/or text label — Running/Waiting/
  Completed/Failed are always readable as words, not inferred from hue
  alone. This is already the pattern in the strongest concepts; it's
  named here as a non-negotiable rule so it survives contact with a
  denser future page that a designer might otherwise be tempted to
  compress into color-only.
- **Keyboard navigation.** Full keyboard operability, including the
  command palette (its entire reason for existing), all table row
  actions, and all modal/drawer dismissal. A visible, high-contrast
  `focus-visible` ring (Section 4.6) on every interactive element —
  explicitly corrected from what the concepts show, which is nothing.
- **Motion.** `prefers-reduced-motion` support as specified in Section
  11, system-wide, not module-by-module.
- **Live regions.** The Activity Timeline and notification bell are
  `aria-live` regions (polite, not assertive — these are informational,
  not urgent interruptions), so a screen-reader user is told about new
  activity without it hijacking their current focus.
- **Map accessibility.** The World Map's information is never
  map-exclusive — every hotspot/country's data is also reachable via a
  keyboard-navigable list view (effectively, the Country Intelligence
  panel's list of active countries functions as this alternate path),
  so the map's visual richness is additive, not a hard requirement to
  use the product.

---

## 13. Long-Term Scalability

- **Multi-tenancy is already a backend fact** (`CompanyProfile`,
  workspace switching) — the design system must not assume a single
  workspace context anywhere; every dashboard/page module fetches
  workspace-scoped data and the workspace switcher (already present as
  `CompanySwitcher`) remains a first-class, always-visible control, not
  a settings-buried option.
- **Design tokens as source of truth.** Given `tailwind.config.js` today
  has zero theme extension, the single highest-leverage implementation
  step is landing Section 4's tokens (color, type scale, spacing,
  elevation) as an actual Tailwind theme extension before any component
  is built against hardcoded values. This is what lets a future light
  theme, or a future rebrand, be a token-file change instead of a
  find-and-replace across hundreds of components.
- **Agent/pipeline extensibility.** As covered in Section 10, new agent
  types and pipeline stages are data, not new components — this matters
  because the backend's own `AGENT_REGISTRY`/`SUPERVISOR_REGISTRY`
  pattern means new agents are a realistic, ongoing occurrence (M7's own
  roadmap already names Research/Email/Reply/Planning agents as future
  additions), and the UI must not require a new component per agent.
- **Internationalization readiness** — numeric/date/currency formatting
  goes through a single formatting layer from day one (even though
  actual translation is deferred, Section 14), so it isn't a retrofit.
- **Live-data assumption must be honest about its transport.** This UI's
  core premise — a continuously live activity feed, live agent status,
  a live map — requires either frequent polling or a real push channel
  (WebSocket/SSE). **The backend has neither today** — every M7 worker
  (Step Runner, Event Dispatcher, Delivery, Mailbox Sync, Thread
  Builder, Reply Intelligence) is a polling background process with no
  push mechanism to a browser client. The design system is specified so
  it works correctly either way (every "live" module is written against
  a data-refresh contract, not an assumption of instant push), which
  means implementation can ship v1 on smart polling (short-interval,
  diffed, no full-page refresh) without a redesign later when/if a real
  push channel is added. Named again in Section 14 since it's a real
  infrastructure gap, not just a design footnote.

---

## 14. Areas Deferred (named explicitly, not silently skipped)

- **Final production logo asset.** Section 6 recommends a direction; an
  actual SVG file (with weight/contrast variants and a favicon-specific
  simplification) does not exist and must be produced before Branding
  can be considered complete.
- **2D vs. 3D world map.** This document specifies the map's *behavior*
  (hotspots, arcs, zoom, country selection, idle beauty) but not its
  rendering technology. A 2D SVG/Canvas map with GeoJSON country shapes
  is the pragmatic, lower-risk implementation path for v1; a WebGL 3D
  globe (three-globe / deck.gl-class tooling) is a legitimate future
  enhancement but a materially larger engineering investment that should
  not be silently assumed into scope. This decision belongs to
  implementation planning, not this document.
- **Real-time transport (WebSocket/SSE).** As covered in Section 13, no
  push infrastructure exists in the backend today. Building one is a
  backend milestone in its own right, not a frontend concern, and is not
  part of M8.
- **`Paused` workflow state.** No backend API exists to pause a running
  `WorkflowInstance`. Either the UI ships without a Paused control until
  that backend capability exists, or a future backend milestone adds it
  — this document takes no position on which, only that the two must be
  decided together, not the UI shipping ahead of a capability it implies
  exists.
- **Full token file / design-tool asset production** (an actual Figma
  library or equivalent). This document defines the tokens' *values and
  rules*; producing pixel-perfect design-tool assets from them is
  implementation-adjacent work, not architecture.
- **Literal migration of the 20 existing pages** into the new IA
  (Section 2's reconciliation table says *where* each page goes; moving
  the code is implementation).
- **Localization/RTL.** Formatting-layer readiness only (Section 13);
  actual translated content and RTL layout mirroring are out of scope.
- **Native mobile app.** The Mobile tier (Section 7) is a responsive web
  experience, not a native app; no native app is proposed here.
- **Charting library selection** (Recharts vs. Nivo vs. visx, etc.) —
  Section 4.6 specifies which chart *types* the system needs and that
  one library is used consistently; the specific library is an
  implementation decision.

---

## Summary

Nine AI-generated concepts, treated as the actual visual foundation of
Sales-Agent4, preserved as closely as possible: the dark, glow-accented,
map-centered Command Center, its dual AI/Sales pipeline widgets, its
funnel chart, its Top Performing Countries ranking, its persistent
quick-action bar, its workspace identity cluster, and its overall density
and composition all carry forward unchanged. Ten corrections were made,
each argued individually in Section 0 against the concepts' own internal
evidence — a handful of duplicated or minority-only elements relocated
to where the concepts' own more complete iterations already put them, a
near-even sidebar-structure call resolved on scalability grounds, one
numeric-progress correctness fix, and one necessary consolidation from
three brand marks to one. That same visual language is now a hard,
per-page requirement (Section 9.1) across Discovery, Research, AI
Workforce, Companies, Contacts, Pipeline, Conversations, Outreach,
Analytics, Settings, and every future module — no page is permitted to
default to a generic admin-panel treatment. A motion system where every
animation must trace to a real backend event, and an explicit accounting
of what this vision needs from the backend that doesn't exist yet
(real-time transport, a pause capability), round out the document rather
than being quietly designed around. Nothing here is authorized for
implementation. The next step is your review.
