import { Bot, Gauge, MessagesSquare, Target, TrendingUp, Users } from "lucide-react";
import { KpiCard } from "./KpiCard";
import type { DashboardProspect } from "./useDashboardPortfolio";
import { averageScore, countNeedsReview } from "./selectors";
import { useAgentActivities } from "../ai-workforce/useAgentActivities";
import { useOpenConversationsCount } from "./useOpenConversationsCount";

/**
 * KpiStrip — Zone 1 Command Strip (Design Bible Section 8). Six cards:
 * five real (three derived from the Prospect list this dashboard already
 * fetches, AI Tasks Running from the real AI Workforce roster - see
 * M8.7 Phase C note below, and Open Conversations from Track C1's real
 * count endpoint - see that note below), one honest placeholder left
 * (Revenue Pipeline - no monetary/deal-value field exists in the backend
 * yet; see docs/architecture/dashboard-capabilities-architecture-plan.md
 * Track C3/C4, not yet built). No fabricated numbers in the remaining
 * placeholder.
 *
 * M8.7 Phase C finding: "AI Tasks Running" was still marked
 * not-implemented with the reason "M7's engine isn't exposed over REST"
 * - true when M8.3 first wrote that, no longer true since M8.4 shipped
 * GET /company-profiles/{id}/ai-workforce/activities (useAgentActivities,
 * the same real roster data TopCommandStrip's AI System pill now uses -
 * see that component's own Phase B note). Leaving this KPI as a
 * placeholder after that API existed would itself have become the
 * dishonest state this whole system argues against - a stale placeholder
 * hiding real data, not a genuine gap. Fixed the same way as the AI
 * System pill: a real count of activities currently `running`, nothing
 * invented beyond what the roster reports.
 *
 * Track C1 (dashboard-capabilities-architecture-plan.md): "Open
 * Conversations" was a placeholder claiming no conversations API route
 * existed - stale even before this track, since M6.5 had already
 * registered app/api/routes/conversations.py; the real gap was that
 * route being scoped to list/detail only, with no aggregate count. Fixed
 * with one new endpoint (GET .../conversations/count) rather than
 * fetching the full open-conversation list just to read its length - see
 * useOpenConversationsCount.ts's own docstring.
 *
 * Track B1 UI refinement - accent/active per card, one honesty note:
 * Needs Review, AI Tasks Running, and now Open Conversations all have
 * real signals to drive `active` from (needsReview/runningCount/count,
 * all computed below). Active Prospects and AI Confidence Score don't
 * have a "something is happening right now" event distinct from "there
 * is a number" - ambient only. Revenue Pipeline is the one remaining
 * honest placeholder - it gets an ambient identity color like every
 * other card, but `active` stays false since there is no real data to
 * make it true from (matching the same "never fabricate liveliness"
 * rule already applied to PipelineFunnel/SalesPipelineWidget/
 * AiRecommendations/MailboxBrief on the dashboard's bottom row).
 */
export function KpiStrip({ prospects, isLoading }: { prospects: DashboardProspect[]; isLoading: boolean }) {
  const avg = averageScore(prospects);
  const needsReview = countNeedsReview(prospects);
  const { activities, isLoading: activitiesLoading } = useAgentActivities();
  const runningCount = activities.filter((activity) => activity.state === "running").length;
  const { count: openConversationsCount, isLoading: conversationsLoading, error: conversationsError } = useOpenConversationsCount();

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
      <KpiCard
        label="Active Prospects"
        icon={Users}
        value={isLoading ? "…" : prospects.length}
        accent="royal-blue"
      />
      <KpiCard
        label="AI Confidence Score"
        icon={Gauge}
        value={isLoading ? "…" : avg !== null ? avg.toFixed(0) : "—"}
        placeholderKind={!isLoading && avg === null ? "no-data" : undefined}
        placeholderReason={!isLoading && avg === null ? "No prospects have been scored yet - the scoring engine is real, there's just nothing to show." : undefined}
        accent="cyan"
      />
      <KpiCard
        label="Needs Review"
        icon={Target}
        value={isLoading ? "…" : needsReview}
        accent="amber"
        active={!isLoading && needsReview > 0}
      />
      <KpiCard
        label="AI Tasks Running"
        icon={Bot}
        value={activitiesLoading ? "…" : runningCount}
        accent="purple"
        active={!activitiesLoading && runningCount > 0}
      />
      <KpiCard
        label="Open Conversations"
        icon={MessagesSquare}
        value={conversationsLoading ? "…" : openConversationsCount ?? "—"}
        placeholderKind={!conversationsLoading && conversationsError ? "no-data" : undefined}
        placeholderReason={!conversationsLoading && conversationsError ? conversationsError : undefined}
        accent="orange"
        active={!conversationsLoading && !conversationsError && (openConversationsCount ?? 0) > 0}
      />
      <KpiCard
        label="Revenue Pipeline"
        icon={TrendingUp}
        placeholderKind="not-implemented"
        placeholderReason="No deal-value field exists in the backend yet."
        accent="gold"
      />
    </div>
  );
}
