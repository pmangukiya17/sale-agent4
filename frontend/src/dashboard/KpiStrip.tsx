import { Bot, Gauge, MessagesSquare, Target, TrendingUp, Users } from "lucide-react";
import { KpiCard } from "./KpiCard";
import type { DashboardProspect } from "./useDashboardPortfolio";
import { averageScore, countNeedsReview } from "./selectors";

/**
 * KpiStrip — Zone 1 Command Strip (Design Bible Section 8). Six cards:
 * three real (derived from the Prospect list this dashboard already
 * fetches), three honest placeholders because no API exists for them yet
 * (see M8.3's constraint analysis - no workflow/supervisor router, no
 * conversations router, no monetary/deal-value field anywhere in the
 * schema). No fabricated numbers in any of the three placeholders.
 */
export function KpiStrip({ prospects, isLoading }: { prospects: DashboardProspect[]; isLoading: boolean }) {
  const avg = averageScore(prospects);
  const needsReview = countNeedsReview(prospects);

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
      <KpiCard
        label="Active Prospects"
        icon={Users}
        value={isLoading ? "…" : prospects.length}
      />
      <KpiCard
        label="AI Confidence Score"
        icon={Gauge}
        value={isLoading ? "…" : avg !== null ? avg.toFixed(0) : "—"}
        placeholderKind={!isLoading && avg === null ? "no-data" : undefined}
        placeholderReason={!isLoading && avg === null ? "No prospects have been scored yet - the scoring engine is real, there's just nothing to show." : undefined}
      />
      <KpiCard
        label="Needs Review"
        icon={Target}
        value={isLoading ? "…" : needsReview}
      />
      <KpiCard
        label="AI Tasks Running"
        icon={Bot}
        placeholderKind="not-implemented"
        placeholderReason="No workflow/agent status API exists yet (M7's engine isn't exposed over REST)."
      />
      <KpiCard
        label="Open Conversations"
        icon={MessagesSquare}
        placeholderKind="not-implemented"
        placeholderReason="No conversations API exists yet - lands with M8.7."
      />
      <KpiCard
        label="Revenue Pipeline"
        icon={TrendingUp}
        placeholderKind="not-implemented"
        placeholderReason="No deal-value field exists in the backend yet."
      />
    </div>
  );
}
