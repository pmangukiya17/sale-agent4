import { useMemo, useState } from "react";
import { ConfirmDialog, PlaceholderNotice, Tabs, useToast } from "../../design-system";
import { useAuth } from "../../auth/AuthContext";
import { useApprovals } from "../../ai-gateway/hooks/useApprovals";
import { useApprovalHistory } from "../../ai-gateway/hooks/useApprovalHistory";
import { ApprovalCard } from "../../ai-gateway/components/ApprovalCard";
import { ApprovalFilterBar } from "../../ai-gateway/components/ApprovalFilterBar";
import type { ApprovalFilterValue } from "../../ai-gateway/components/ApprovalFilterBar";
import { ApprovalHistoryTable } from "../../ai-gateway/components/ApprovalHistoryTable";
import type { ApprovalRequest } from "../../ai-gateway/types";

type PendingAction = { request: ApprovalRequest; decision: "approve" | "reject" };

/**
 * AIGatewayApprovals — /ai-gateway/approvals. M8.3 Step 7 (Premium
 * Approval UI): Approve/Reject are now real mutations (see useApprovals.ts's
 * own docstring for the "not yet implemented" Toast this replaces), gated
 * behind a `ConfirmDialog` (the shared design-system confirmation
 * primitive, same one M8.17's Global Delete System already established -
 * see that component's own docstring) rather than firing immediately on
 * click, since granting/recording a premium pre-authorization is a real,
 * consequential action now. History is a real `Tabs`-switched table (GET
 * /ai-gateway/approvals/history), replacing the prior PlaceholderNotice.
 *
 * Both Approve/Reject and the History tab are admin-gated server-side
 * (CEO decision, 2026-07-29 - see GatewayDataProvider.ts's own docstring)
 * - `isAdmin` below is a client-side courtesy only, same convention
 * `ModelRoleManagementPanel.tsx` already established: a non-admin still
 * sees every approval-required event and its current status, just without
 * the ability to act on it or view the decision history.
 */
export default function AIGatewayApprovals() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const { data: approvals, isLoading, error, isMutating, approve, reject } = useApprovals();
  const history = useApprovalHistory({ enabled: isAdmin });
  const { showToast } = useToast();

  const [filter, setFilter] = useState<ApprovalFilterValue>("pending");
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);

  const counts = useMemo(() => {
    const base: Record<ApprovalFilterValue, number> = { all: approvals.length, pending: 0, approved: 0, rejected: 0 };
    for (const a of approvals) base[a.status] += 1;
    return base;
  }, [approvals]);

  const filtered = filter === "all" ? approvals : approvals.filter((a) => a.status === filter);

  function requestApprove(request: ApprovalRequest) {
    setPendingAction({ request, decision: "approve" });
  }
  function requestReject(request: ApprovalRequest) {
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
      if (isAdmin) history.refresh();
      setPendingAction(null);
    } catch {
      showToast({ message: `Could not ${decision} "${request.feature}".`, tone: "danger" });
    }
  }

  const pendingQueue = (
    <div className="flex flex-col gap-4">
      <ApprovalFilterBar value={filter} onChange={setFilter} counts={counts} />
      {error && <p className="text-sm text-status-danger">{error}</p>}
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : filtered.length === 0 ? (
        <PlaceholderNotice
          kind="no-data"
          reason={filter === "pending" ? "Nothing needs your approval right now." : `No ${filter} approvals.`}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {filtered.map((request) => (
            <ApprovalCard
              key={request.id}
              request={request}
              canDecide={isAdmin}
              isMutating={isMutating}
              onApprove={requestApprove}
              onReject={requestReject}
            />
          ))}
        </div>
      )}
    </div>
  );

  const historyPanel = isAdmin ? (
    <ApprovalHistoryTable rows={history.data} isLoading={history.isLoading} />
  ) : (
    <PlaceholderNotice kind="no-data" reason="Approval history is admin-only." />
  );

  return (
    <div className="flex flex-col gap-6">
      <Tabs
        items={[
          { id: "pending", label: "Queue", content: pendingQueue },
          { id: "history", label: "History", content: historyPanel },
        ]}
      />

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
