import { useState } from "react";
import { StatusIndicator, Table } from "../../design-system";
import type { StatusKind, TableColumn } from "../../design-system";
import { useActivity } from "../../ai-gateway/hooks/useActivity";
import { ProviderChip } from "../../ai-gateway/components/ProviderChip";
import { CostPill } from "../../ai-gateway/components/CostPill";
import { ActivityDetailDrawer } from "../../ai-gateway/components/ActivityDetailDrawer";
import type { ActivityLogEntry } from "../../ai-gateway/types";

const STATUS_DISPLAY: Record<ActivityLogEntry["status"], { kind: StatusKind; label: string }> = {
  success: { kind: "success", label: "Success" },
  waiting: { kind: "waiting", label: "Waiting" },
  failed: { kind: "failed", label: "Failed" },
};

/**
 * AIGatewayActivity — /ai-gateway/activity. Reuses `Table` as-is (no
 * design-system change). Row click opens `ActivityDetailDrawer`
 * (SlideOver) rather than navigating - see that component's docstring for
 * why a drawer, not a route push, keeps the log scannable.
 */
export default function AIGatewayActivity() {
  const { data: activity, isLoading, error } = useActivity();
  const [selected, setSelected] = useState<ActivityLogEntry | null>(null);

  const columns: TableColumn<ActivityLogEntry>[] = [
    {
      key: "time",
      header: "Time",
      render: (row) => new Date(row.timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
      sortable: true,
      sortValue: (row) => row.timestamp,
    },
    { key: "feature", header: "Feature", render: (row) => row.feature },
    { key: "agent", header: "Agent", render: (row) => row.agent },
    {
      key: "provider",
      header: "Provider",
      render: (row) => (row.providerKey ? <ProviderChip providerKey={row.providerKey} linked={false} /> : "—"),
    },
    { key: "cost", header: "Cost", render: (row) => <CostPill usd={row.costUsd} />, align: "right" },
    {
      key: "latency",
      header: "Latency",
      render: (row) => (row.latencyMs ? `${row.latencyMs}ms` : "—"),
      align: "right",
      sortable: true,
      sortValue: (row) => row.latencyMs ?? 0,
    },
    {
      key: "status",
      header: "Status",
      render: (row) => <StatusIndicator kind={STATUS_DISPLAY[row.status].kind} label={STATUS_DISPLAY[row.status].label} />,
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="text-sm text-status-danger">{error}</p>}
      <Table
        columns={columns}
        rows={activity}
        rowKey={(row) => row.id}
        isLoading={isLoading}
        emptyMessage="No AI Gateway activity yet."
        onRowClick={(row) => setSelected(row)}
      />
      <ActivityDetailDrawer entry={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
