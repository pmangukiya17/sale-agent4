import { Coins, Hash, Percent } from "lucide-react";
import { PlaceholderNotice } from "../../design-system";
import { KpiCard } from "../../dashboard/KpiCard";
import { useActivity } from "../../ai-gateway/hooks/useActivity";

/**
 * AIGatewayUsage — /ai-gateway/usage. Charts (daily cost, monthly trend,
 * provider distribution) are this page's primary requested content and
 * are explicitly out of scope this milestone (no charting library
 * installed, none approved for this pass - see the implementation
 * report). Rather than leave the page blank, three real KPIs are
 * computed client-side from the same mock activity log Activity/Overview
 * already use (no new hook, no new fixture), and the chart area is one
 * honest PlaceholderNotice.
 */
export default function AIGatewayUsage() {
  const { data: activity, isLoading } = useActivity();

  const totalCost = activity.reduce((sum, entry) => sum + (entry.costUsd ?? 0), 0);
  const completedCount = activity.filter((entry) => entry.status !== "waiting").length;
  const avgCost = completedCount > 0 ? totalCost / completedCount : 0;
  const successCount = activity.filter((entry) => entry.status === "success").length;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <KpiCard
          label="Total Cost (log)"
          value={isLoading ? undefined : `$${totalCost.toFixed(4)}`}
          icon={Coins}
          accent="orange"
        />
        <KpiCard
          label="Avg Cost / Request"
          value={isLoading ? undefined : `$${avgCost.toFixed(4)}`}
          icon={Hash}
          accent="teal"
        />
        <KpiCard
          label="Requests Logged"
          value={isLoading ? undefined : `${successCount} / ${activity.length}`}
          icon={Percent}
          accent="gold"
        />
      </div>

      <PlaceholderNotice
        kind="not-implemented"
        reason="Daily/monthly cost charts and provider distribution — charts are out of scope for this foundation milestone. See docs/architecture/ai-gateway-ux-architecture.md Section 9 for the recommended charting approach."
      />
    </div>
  );
}
