import { Badge, Card, Button } from "../../design-system";
import { ProviderChip } from "./ProviderChip";
import { CostPill } from "./CostPill";
import type { ApprovalRequest } from "../types";

const STATUS_BADGE_TONE: Record<ApprovalRequest["status"], "warning" | "success" | "danger"> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
};

/**
 * ApprovalCard — one premium-approval-required event (Premium Approval
 * Center + its Overview preview). `accent="amber"` is the one place in
 * this zone amber is used as a card's ambient identity rather than only a
 * Badge tone, deliberately, so pending approvals visually stand apart from
 * the calm blues/greens/violets everywhere else in the AI Gateway pages
 * (approved architecture doc, Section 7.2). `active` is only true while
 * `status === "pending"` (M8.3 Step 7 change - previously always true, back
 * when every row shown here was implicitly still pending) - a decided row
 * is no longer "live" the way an unresolved one is.
 *
 * M8.3 Step 7 (Premium Approval UI): `onApprove`/`onReject` are now real
 * mutations at the call site (see useApprovals.ts's own docstring for the
 * prior "not yet implemented" Toast this replaces). Buttons only render
 * when `status === "pending"` AND `canDecide` is true - a row whose
 * (company, capability) pair has already been decided shows a status
 * `Badge` instead (nothing left to action against for THIS row, even
 * though other pending rows for the same pair would also flip if acted on
 * - see ApprovalRequestRead.status's own docstring in ../types.ts).
 * `canDecide` is a client-side courtesy only (same convention
 * ModelRoleManagementPanel.tsx already established for its own admin-only
 * writes) - the backend independently 403s a non-admin's approve/reject
 * call regardless of what this component renders.
 */
export function ApprovalCard({
  request,
  canDecide = true,
  isMutating = false,
  onApprove,
  onReject,
}: {
  request: ApprovalRequest;
  canDecide?: boolean;
  isMutating?: boolean;
  onApprove: (request: ApprovalRequest) => void;
  onReject: (request: ApprovalRequest) => void;
}) {
  const isPending = request.status === "pending";
  return (
    <Card accent="amber" active={isPending} className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">{request.feature}</h3>
          {request.companyName && <p className="text-xs text-slate-500">{request.companyName}</p>}
        </div>
        {isPending ? (
          <span className="shrink-0 text-xs font-medium text-status-warning">{request.waitingMinutes}m waiting</span>
        ) : (
          <Badge tone={STATUS_BADGE_TONE[request.status]} className="shrink-0">
            {request.status}
          </Badge>
        )}
      </div>

      <p className="text-xs text-slate-400">{request.reason}</p>

      <dl className="grid grid-cols-2 gap-2 text-xs text-slate-500">
        <div>
          <dt className="text-[10px] uppercase tracking-wide">Provider</dt>
          <dd className="mt-0.5">
            <ProviderChip providerKey={request.providerKey} />
          </dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-wide">Est. cost</dt>
          <dd className="mt-0.5">
            <CostPill usd={request.estimatedCostUsd} />
          </dd>
        </div>
      </dl>

      {isPending && canDecide && (
        <div className="mt-1 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={() => onReject(request)} disabled={isMutating}>
            Reject
          </Button>
          <Button variant="primary" size="sm" onClick={() => onApprove(request)} disabled={isMutating}>
            Approve
          </Button>
        </div>
      )}
      {isPending && !canDecide && (
        <p className="mt-1 text-right text-[11px] text-slate-500">Admin required to approve or reject.</p>
      )}
    </Card>
  );
}
