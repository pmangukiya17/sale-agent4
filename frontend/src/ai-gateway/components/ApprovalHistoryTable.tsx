import { Badge, Table } from "../../design-system";
import type { TableColumn } from "../../design-system";
import { CostPill } from "./CostPill";
import type { PremiumPreauthorization } from "../types";

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

/**
 * ApprovalHistoryTable — M8.3 Step 7 (Premium Approval UI). GET
 * /ai-gateway/approvals/history's read surface, replacing the previous
 * PlaceholderNotice ("not yet implemented in this foundation milestone")
 * on AIGatewayApprovals.tsx. Built on the shared `Table` design-system
 * primitive (Design Bible Section 4.6) - same "one table system" rule
 * every other List page in this app already follows - rather than a new,
 * one-off list markup.
 *
 * Every row here IS a decision (`decision` is always "approved"/"rejected",
 * never "pending" - see PremiumPreauthorization's own docstring in
 * ../types.ts) - this is the append-only audit trail, not the actionable
 * queue (`ApprovalCard`/the Pending tab own that).
 */
export function ApprovalHistoryTable({ rows, isLoading }: { rows: PremiumPreauthorization[]; isLoading: boolean }) {
  const columns: TableColumn<PremiumPreauthorization>[] = [
    {
      key: "feature",
      header: "Feature",
      render: (row) => (
        <div>
          <div className="font-medium text-slate-200">{row.feature}</div>
          {row.companyName && <div className="text-[11px] text-slate-500">{row.companyName}</div>}
        </div>
      ),
      sortable: true,
      sortValue: (row) => row.feature,
    },
    {
      key: "decision",
      header: "Decision",
      render: (row) => <Badge tone={row.decision === "approved" ? "success" : "danger"}>{row.decision}</Badge>,
      sortable: true,
      sortValue: (row) => row.decision,
    },
    {
      key: "decidedBy",
      header: "Decided By",
      render: (row) => row.decidedBy ?? "—",
    },
    {
      key: "decidedAt",
      header: "Decided At",
      render: (row) => formatDateTime(row.decidedAt),
      sortable: true,
      sortValue: (row) => row.decidedAt,
      align: "right",
    },
    {
      key: "expiresAt",
      header: "Expires",
      render: (row) => (row.expiresAt ? formatDateTime(row.expiresAt) : "—"),
      align: "right",
    },
    {
      key: "sourceEstimatedCostUsd",
      header: "Est. Cost",
      render: (row) => <CostPill usd={row.sourceEstimatedCostUsd} />,
      align: "right",
    },
  ];

  return (
    <Table
      columns={columns}
      rows={rows}
      rowKey={(row) => row.id}
      isLoading={isLoading}
      emptyMessage="No approval decisions recorded yet."
    />
  );
}
