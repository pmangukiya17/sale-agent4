import { Bot, Gauge, MessagesSquare, Target, TrendingUp, Users } from "lucide-react";
import { KpiCard } from "./KpiCard";
import type { DashboardProspect } from "./useDashboardPortfolio";
import { averageScore, countNeedsReview } from "./selectors";
import { useAgentActivities } from "../ai-workforce/useAgentActivities";
import { useOpenConversationsCount } from "./useOpenConversationsCount";
import { useOpportunityPipelineValue } from "./useOpportunityPipelineValue";

/**
 * formatCurrencyValue — best-effort Intl.NumberFormat currency
 * formatting for one pipeline-value row. `currency` is nullable (an
 * Opportunity with no currency set yet) - Intl.NumberFormat can't format
 * `style: "currency"` without a real ISO code, so that case falls back
 * to a plain formatted number with no currency symbol, rather than
 * guessing one.
 */
function formatCurrencyValue(value: number, currency: string | null): string {
  if (!currency) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
  } catch {
    return `${value.toLocaleString(undefined, { maximumFractionDigits: 0 })} ${currency}`;
  }
}

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
 * Track C4 (dashboard-capabilities-architecture-plan.md, Section 4):
 * "Revenue Pipeline" moved from an honest placeholder to real data - the
 * real Opportunity domain Track C3 built now backs it via
 * GET .../opportunities/pipeline-value, one row per distinct currency in
 * use (the Track C4 fix for the architecture doc's own Section 4.10
 * currency-mixing decision - see useOpportunityPipelineValue.ts's own
 * docstring). In the common single-currency case the card shows that one
 * formatted total; a business with genuinely mixed currencies shows the
 * largest currency's total with a "+N" note rather than ever blending
 * them into one meaningless summed number.
 *
 * Track B1 UI refinement - accent/active per card, one honesty note:
 * Needs Review, AI Tasks Running, Open Conversations, and now Revenue
 * Pipeline all have real signals to drive `active` from (needsReview/
 * runningCount/count/pipeline value, all computed below). Active
 * Prospects and AI Confidence Score don't have a "something is happening
 * right now" event distinct from "there is a number" - ambient only.
 */
export function KpiStrip({ prospects, isLoading }: { prospects: DashboardProspect[]; isLoading: boolean }) {
  const avg = averageScore(prospects);
  const needsReview = countNeedsReview(prospects);
  const { activities, isLoading: activitiesLoading } = useAgentActivities();
  const runningCount = activities.filter((activity) => activity.state === "running").length;
  const { count: openConversationsCount, isLoading: conversationsLoading, error: conversationsError } = useOpenConversationsCount();
  const {
    breakdown: pipelineValueBreakdown,
    isLoading: pipelineValueLoading,
    error: pipelineValueError,
  } = useOpportunityPipelineValue();
  const primaryPipelineRow = [...pipelineValueBreakdown].sort(
    (a, b) => b.open_pipeline_value - a.open_pipeline_value
  )[0];
  const revenuePipelineValue = primaryPipelineRow
    ? pipelineValueBreakdown.length === 1
      ? formatCurrencyValue(primaryPipelineRow.open_pipeline_value, primaryPipelineRow.currency)
      : `${formatCurrencyValue(primaryPipelineRow.open_pipeline_value, primaryPipelineRow.currency)} +${
          pipelineValueBreakdown.length - 1
        }`
    : undefined;

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
        value={pipelineValueLoading ? "…" : revenuePipelineValue ?? "—"}
        placeholderKind={!pipelineValueLoading && (pipelineValueError || !primaryPipelineRow) ? "no-data" : undefined}
        placeholderReason={
          !pipelineValueLoading && pipelineValueError
            ? pipelineValueError
            : !pipelineValueLoading && !primaryPipelineRow
              ? "No opportunities yet - the Opportunity domain is real, there's just nothing here."
              : undefined
        }
        accent="gold"
        active={!pipelineValueLoading && !pipelineValueError && Boolean(primaryPipelineRow) && primaryPipelineRow.open_pipeline_value > 0}
      />
    </div>
  );
}
