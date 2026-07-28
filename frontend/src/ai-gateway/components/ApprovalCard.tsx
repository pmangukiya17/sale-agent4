import { Card, Button } from "../../design-system";
import { ProviderChip } from "./ProviderChip";
import { CostPill } from "./CostPill";
import type { ApprovalRequest } from "../types";

/**
 * ApprovalCard — one pending premium-approval request (Premium Approval
 * Center + its Overview preview). `accent="amber"` is the one place in
 * this zone amber is used as a card's ambient identity rather than only a
 * Badge tone, deliberately, so pending approvals visually stand apart from
 * the calm blues/greens/violets everywhere else in the AI Gateway pages
 * (approved architecture doc, Section 7.2). `active` is intentionally
 * always true here - a pending approval is inherently "live" for its
 * entire time on screen, a real, always-true signal, not a fabricated one.
 *
 * `onApprove`/`onReject` are plain callbacks, not wired to any backend
 * mutation in this milestone (approval workflow execution is explicitly
 * out of scope) - the pages using this component pass handlers that show
 * an honest Toast ("Not yet implemented") rather than either faking
 * success or disabling the buttons outright.
 */
export function ApprovalCard({
  request,
  onApprove,
  onReject,
}: {
  request: ApprovalRequest;
  onApprove: (request: ApprovalRequest) => void;
  onReject: (request: ApprovalRequest) => void;
}) {
  return (
    <Card accent="amber" active className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">{request.feature}</h3>
          {request.companyName && <p className="text-xs text-slate-500">{request.companyName}</p>}
        </div>
        <span className="shrink-0 text-xs font-medium text-status-warning">{request.waitingMinutes}m waiting</span>
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

      <div className="mt-1 flex justify-end gap-2">
        <Button variant="secondary" size="sm" onClick={() => onReject(request)}>
          Reject
        </Button>
        <Button variant="primary" size="sm" onClick={() => onApprove(request)}>
          Approve
        </Button>
      </div>
    </Card>
  );
}
