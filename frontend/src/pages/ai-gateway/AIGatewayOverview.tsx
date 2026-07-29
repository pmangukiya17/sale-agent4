import { useState } from "react";
import { Bot, Cpu, DollarSign, Gauge, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, ConfirmDialog, PlaceholderNotice, useToast } from "../../design-system";
import { useAuth } from "../../auth/AuthContext";
import { KpiCard } from "../../dashboard/KpiCard";
import { useGatewayOverview } from "../../ai-gateway/hooks/useGatewayOverview";
import { useActivity } from "../../ai-gateway/hooks/useActivity";
import { useApprovals } from "../../ai-gateway/hooks/useApprovals";
import { ApprovalCard } from "../../ai-gateway/components/ApprovalCard";
import { ProviderChip } from "../../ai-gateway/components/ProviderChip";
import type { ApprovalRequest } from "../../ai-gateway/types";

type PendingAction = { request: ApprovalRequest; decision: "approve" | "reject" };

const HEALTH_LABEL: Record<string, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  down: "Down",
};

/**
 * AIGatewayOverview — /ai-gateway. Real, mock-backed content for the KPI
 * row, a recent-activity snapshot, and the top pending approvals; charts
 * (Provider Mix, Cost Trend) are explicitly out of scope this milestone,
 * so that space renders an honest PlaceholderNotice instead of a
 * fabricated chart or an empty gap.
 */
export default function AIGatewayOverview() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const { data: overview, isLoading: overviewLoading } = useGatewayOverview();
  const { data: activity, isLoading: activityLoading } = useActivity();
  const { data: approvals, isLoading: approvalsLoading, isMutating, approve, reject } = useApprovals();
  const { showToast } = useToast();

  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const pendingApprovals = approvals.filter((a) => a.status === "pending");

  function handleApprove(request: ApprovalRequest) {
    setPendingAction({ request, decision: "approve" });
  }
  function handleReject(request: ApprovalRequest) {
    setPendingAction({ request, decision: "reject" });
  }
  function cancelAction() {
    if (isMutating) return;
    setPendingAction(null);
  }
  async function confirmAction() {
    if (!pendingAction) return;
    const { request, decision } = pendingAction;
    try {
      if (decision === "approve") {
        await approve(request.id);
        showToast({ message: `Approved premium access for "${request.feature}".`, tone: "success" });
      } else {
        await reject(request.id);
        showToast({ message: `Rejected "${request.feature}".`, tone: "neutral" });
      }
      setPendingAction(null);
    } catch {
      showToast({ message: `Could not ${decision} "${request.feature}".`, tone: "danger" });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-7">
        <KpiCard
          label="Gateway Health"
          value={overview ? HEALTH_LABEL[overview.gatewayHealth] : undefined}
          icon={ShieldCheck}
          accent="emerald"
          placeholderKind={!overviewLoading && !overview ? "no-data" : undefined}
        />
        <KpiCard
          label="Active Providers"
          value={overview ? `${overview.activeProviders} / ${overview.totalProviders}` : undefined}
          icon={Cpu}
          accent="cyan"
        />
        <KpiCard
          label="Running Agents"
          value={overview?.runningAgents}
          icon={Bot}
          accent="royal-blue"
          active={Boolean(overview && overview.runningAgents > 0)}
        />
        <KpiCard label="Today's Requests" value={overview?.requestsToday} icon={TrendingUp} accent="teal" />
        <KpiCard
          label="Success Rate"
          value={overview ? `${overview.successRatePct}%` : undefined}
          icon={Gauge}
          accent="gold"
        />
        <KpiCard
          label="Est. Cost Today"
          value={overview ? `$${overview.estimatedCostTodayUsd.toFixed(2)}` : undefined}
          icon={DollarSign}
          accent="orange"
        />
        <KpiCard label="Premium Requests" value={overview?.premiumRequestsToday} icon={Sparkles} accent="indigo" />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-100">Recent Activity</h2>
            <Link to="/ai-gateway/activity" className="text-xs font-medium text-accent-primary hover:underline">
              View full log →
            </Link>
          </div>
          {activityLoading ? (
            <p className="text-xs text-slate-500">Loading…</p>
          ) : activity.length === 0 ? (
            <PlaceholderNotice kind="no-data" reason="No AI Gateway activity yet." />
          ) : (
            <ul className="flex flex-col gap-2">
              {activity.slice(0, 5).map((entry) => (
                <li key={entry.id} className="flex items-center justify-between gap-3 text-xs">
                  <span className="text-slate-400">{entry.feature}</span>
                  {entry.providerKey ? <ProviderChip providerKey={entry.providerKey} /> : <span className="text-slate-600">—</span>}
                  <span
                    className={
                      entry.status === "success"
                        ? "text-status-success"
                        : entry.status === "waiting"
                        ? "text-status-warning"
                        : "text-status-danger"
                    }
                  >
                    {entry.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-100">Pending Premium Approvals</h2>
            <Link to="/ai-gateway/approvals" className="text-xs font-medium text-accent-primary hover:underline">
              View all approvals →
            </Link>
          </div>
          {approvalsLoading ? (
            <p className="text-xs text-slate-500">Loading…</p>
          ) : pendingApprovals.length === 0 ? (
            <PlaceholderNotice kind="no-data" reason="Nothing needs your approval right now." />
          ) : (
            <div className="flex flex-col gap-3">
              {pendingApprovals.slice(0, 2).map((request) => (
                <ApprovalCard
                  key={request.id}
                  request={request}
                  canDecide={isAdmin}
                  isMutating={isMutating}
                  onApprove={handleApprove}
                  onReject={handleReject}
                />
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <PlaceholderNotice
          kind="not-implemented"
          reason="Provider mix chart — charts are out of scope for this foundation milestone."
        />
        <PlaceholderNotice
          kind="not-implemented"
          reason="7-day cost trend chart — charts are out of scope for this foundation milestone."
        />
      </div>

      <ConfirmDialog
        open={pendingAction !== null}
        title={pendingAction?.decision === "reject" ? "Reject this request?" : "Approve premium access?"}
        message={
          pendingAction
            ? pendingAction.decision === "approve"
              ? `This pre-authorizes premium access for "${pendingAction.request.feature}"${
                  pendingAction.request.companyName ? ` (${pendingAction.request.companyName})` : ""
                } for the next 120 minutes. It does not resume this specific request — the next matching one will go through automatically.`
              : `This records a rejection for "${pendingAction.request.feature}"${
                  pendingAction.request.companyName ? ` (${pendingAction.request.companyName})` : ""
                }. It's an audit annotation only — nothing is unblocked or undone.`
            : ""
        }
        confirmLabel={pendingAction?.decision === "reject" ? "Reject" : "Approve"}
        tone={pendingAction?.decision === "reject" ? "danger" : "neutral"}
        isLoading={isMutating}
        onConfirm={confirmAction}
        onCancel={cancelAction}
      />
    </div>
  );
}
