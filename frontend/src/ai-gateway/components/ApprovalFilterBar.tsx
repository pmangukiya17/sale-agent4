import { cn } from "../../design-system";
import type { ApprovalStatus } from "../types";

export type ApprovalFilterValue = "all" | ApprovalStatus;

const FILTERS: { value: ApprovalFilterValue; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

/**
 * ApprovalFilterBar — M8.3 Step 7 (Premium Approval UI). A plain
 * segmented control over `ApprovalRequest.status` (see that field's own
 * docstring in ../types.ts) - client-side filtering over whatever
 * `useApprovals()` already fetched, same "no business logic in
 * presentation components" convention `Table`'s own sort mechanics
 * already follow. Defaults to "pending" at the call site (see
 * AIGatewayApprovals.tsx) since that's the one actionable queue this page
 * exists for; "Approved"/"Rejected"/"All" exist so a decision already made
 * (elsewhere, or by someone else) doesn't just disappear from view.
 */
export function ApprovalFilterBar({
  value,
  onChange,
  counts,
}: {
  value: ApprovalFilterValue;
  onChange: (value: ApprovalFilterValue) => void;
  counts: Record<ApprovalFilterValue, number>;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Filter approvals by status">
      {FILTERS.map((filter) => (
        <button
          key={filter.value}
          type="button"
          role="tab"
          aria-selected={value === filter.value}
          onClick={() => onChange(filter.value)}
          className={cn(
            "rounded-pill border px-3 py-1 text-xs font-medium transition-colors",
            value === filter.value
              ? "border-accent-primary/40 bg-accent-primary/10 text-accent-primary"
              : "border-border-hairline bg-surface-1 text-slate-400 hover:text-slate-200"
          )}
        >
          {filter.label}
          <span className="ml-1.5 text-slate-500">{counts[filter.value]}</span>
        </button>
      ))}
    </div>
  );
}
