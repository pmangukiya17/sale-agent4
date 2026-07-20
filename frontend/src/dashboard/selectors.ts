import type { DashboardProspect } from "./useDashboardPortfolio";

/**
 * Pure aggregation functions over already-fetched dashboard data. Kept
 * separate from every widget component on purpose (the milestone's "no
 * business logic in presentation components" requirement) - a widget only
 * ever calls one of these and renders the result, it never reaches into
 * `prospects`/`companies` arrays itself. Also what makes these numbers
 * testable without mounting React at all.
 */

const isToday = (isoDate: string): boolean => {
  const d = new Date(isoDate);
  const now = new Date();
  return (
    d.getUTCFullYear() === now.getUTCFullYear() &&
    d.getUTCMonth() === now.getUTCMonth() &&
    d.getUTCDate() === now.getUTCDate()
  );
};

export function averageScore(prospects: DashboardProspect[]): number | null {
  const scored = prospects.filter((p) => typeof p.total_score === "number") as (DashboardProspect & {
    total_score: number;
  })[];
  if (scored.length === 0) return null;
  return scored.reduce((sum, p) => sum + p.total_score, 0) / scored.length;
}

export function countNeedsReview(prospects: DashboardProspect[]): number {
  return prospects.filter((p) => p.status === "scored" || p.status === "in_review").length;
}

export function todaysSummary(prospects: DashboardProspect[]) {
  return {
    discoveredToday: prospects.filter((p) => isToday(p.first_discovered_at)).length,
    reviewedToday: prospects.filter((p) => p.reviewed_at && isToday(p.reviewed_at)).length,
    seenToday: prospects.filter((p) => isToday(p.last_seen_at)).length,
  };
}

/** Human labels for the real ProspectStatus enum values (backend/app/models/enums.py) - the AI Pipeline widget's stage vocabulary, since Prospect.status is the only real field describing where the AI engines have taken a prospect so far. */
export const PROSPECT_STATUS_LABELS: Record<string, string> = {
  new: "New",
  duplicate_review: "Duplicate Review",
  scored: "Scored",
  qualified: "Qualified",
  unqualified: "Unqualified",
  in_review: "In Review",
  approved: "Approved",
  rejected: "Rejected",
  archived: "Archived",
};

export const PROSPECT_STATUS_ORDER = [
  "new",
  "duplicate_review",
  "scored",
  "in_review",
  "qualified",
  "approved",
  "unqualified",
  "rejected",
  "archived",
];

export function countByStatus(prospects: DashboardProspect[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const p of prospects) counts[p.status] = (counts[p.status] ?? 0) + 1;
  return counts;
}

/** Human labels for the real, legacy PipelineStage enum values (backend/app/models/enums.py) that the M0 Company model still uses - see SalesPipelineWidget.tsx / PipelineFunnel.tsx for why this, not an invented deal-stage vocabulary, is what's actually real today. */
export const LEGACY_STAGE_LABELS: Record<string, string> = {
  discovered: "Discovered",
  enriched: "Enriched",
  verified: "Verified",
  website_analyzed: "Website Analyzed",
  qualified: "Qualified",
  disqualified: "Disqualified",
  contact_found: "Contact Found",
  draft_generated: "Draft Generated",
  pending_approval: "Pending Approval",
  sent: "Sent",
  replied: "Replied",
  no_reply: "No Reply",
  follow_up_1: "Follow-up 1",
  follow_up_2: "Follow-up 2",
  follow_up_3: "Follow-up 3",
  won: "Won",
  lost: "Lost",
  nurture: "Nurture",
};

export const LEGACY_STAGE_ORDER = Object.keys(LEGACY_STAGE_LABELS);

// FUNNEL_GROUPS/countByLegacyStage (a legacy-Company.stage grouping for
// PipelineFunnel's now-removed bar chart) were removed in M8.7 Phase C -
// see PipelineFunnel.tsx's own docstring for why rendering that legacy
// model as a "conversion funnel" was an honesty regression, the same one
// SalesPipelineWidget was already corrected for. LEGACY_STAGE_LABELS/
// LEGACY_STAGE_ORDER above are unaffected - still real, still used by
// the legacy Pipeline.tsx list view itself.

export interface CountryAggregate {
  country: string;
  count: number;
  avgScore: number | null;
}

export function aggregateByCountry(prospects: DashboardProspect[]): CountryAggregate[] {
  const groups = new Map<string, DashboardProspect[]>();
  for (const p of prospects) {
    if (!p.country) continue;
    const list = groups.get(p.country) ?? [];
    list.push(p);
    groups.set(p.country, list);
  }
  return Array.from(groups.entries())
    .map(([country, list]) => ({
      country,
      count: list.length,
      avgScore: averageScore(list),
    }))
    .sort((a, b) => b.count - a.count);
}

export function topPerformingCountries(prospects: DashboardProspect[], limit = 5): CountryAggregate[] {
  return [...aggregateByCountry(prospects)]
    .filter((c) => c.avgScore !== null)
    .sort((a, b) => (b.avgScore ?? 0) - (a.avgScore ?? 0))
    .slice(0, limit);
}

export interface RecentActivityItem {
  id: string;
  name: string;
  country: string | null;
  status: string;
  at: string;
  kind: "discovered" | "reviewed" | "seen";
}

/** Reusable "recent activity" feed built from real Prospect timestamps
 * (first_discovered_at / reviewed_at / last_seen_at) - not per-event, since
 * no cross-portfolio timeline endpoint exists (prospect_timeline.py is
 * scoped to a single prospect only). See ActivityTimeline.tsx's docstring. */
export function recentActivity(prospects: DashboardProspect[], limit = 8): RecentActivityItem[] {
  const events: RecentActivityItem[] = [];
  for (const p of prospects) {
    events.push({ id: `${p.id}-discovered`, name: p.name, country: p.country, status: p.status, at: p.first_discovered_at, kind: "discovered" });
    if (p.reviewed_at) {
      events.push({ id: `${p.id}-reviewed`, name: p.name, country: p.country, status: p.status, at: p.reviewed_at, kind: "reviewed" });
    }
  }
  return events.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime()).slice(0, limit);
}

export function needsReviewList(prospects: DashboardProspect[], limit = 5): DashboardProspect[] {
  return prospects
    .filter((p) => p.status === "scored" || p.status === "in_review")
    .sort((a, b) => (b.total_score ?? 0) - (a.total_score ?? 0))
    .slice(0, limit);
}
