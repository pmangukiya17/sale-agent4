import { PlaceholderNotice, useToast } from "../../design-system";
import { useApprovals } from "../../ai-gateway/hooks/useApprovals";
import { ApprovalCard } from "../../ai-gateway/components/ApprovalCard";
import type { ApprovalRequest } from "../../ai-gateway/types";

/**
 * AIGatewayApprovals — /ai-gateway/approvals. Pending queue is real
 * (mock-backed); Approve/Reject execution and a History tab are
 * explicitly out of scope this milestone (approval workflow execution),
 * so the buttons surface an honest Toast instead of mutating state, and
 * History is one PlaceholderNotice rather than a fabricated empty table.
 */
export default function AIGatewayApprovals() {
  const { data: approvals, isLoading, error } = useApprovals();
  const { showToast } = useToast();

  function handleApprove(request: ApprovalRequest) {
    showToast({ message: `Approval workflow is not yet implemented (${request.feature}).`, tone: "neutral" });
  }
  function handleReject(request: ApprovalRequest) {
    showToast({ message: `Approval workflow is not yet implemented (${request.feature}).`, tone: "neutral" });
  }

  return (
    <div className="flex flex-col gap-6">
      {error && <p className="text-sm text-status-danger">{error}</p>}
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : approvals.length === 0 ? (
        <PlaceholderNotice kind="no-data" reason="Nothing needs your approval right now." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {approvals.map((request) => (
            <ApprovalCard key={request.id} request={request} onApprove={handleApprove} onReject={handleReject} />
          ))}
        </div>
      )}

      <PlaceholderNotice kind="not-implemented" reason="Approval history — not yet implemented in this foundation milestone." />
    </div>
  );
}
