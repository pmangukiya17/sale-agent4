import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Card, PlaceholderNotice, Table, Tabs } from "../design-system";
import type { BadgeTone, TableColumn } from "../design-system";
import { useCompanies } from "../companies/CompanyContext";
import { useDashboardPortfolio } from "../dashboard/useDashboardPortfolio";
import { KpiCard } from "../dashboard/KpiCard";
import {
  PROSPECT_STATUS_LABELS,
  PROSPECT_STATUS_ORDER,
  aggregateByCountry,
  averageScore,
  countByStatus,
  countNeedsReview,
  type CountryAggregate,
} from "../dashboard/selectors";
import { useAnalytics, fetchCampaignQueueStats, type JobHealthSummary, type CampaignQueueStats } from "../analytics/useAnalytics";
import { BarChart3, Layers, Star, Users } from "lucide-react";

/**
 * Analytics — M8.9. Purpose-built page per the IA reconciliation table
 * ("charts + rankings, the home for everything cut from the dashboard")
 * and Section 9.1 (reuse the same chart vocabulary at larger scale, not a
 * different visual language) - built ENTIRELY from data the backend
 * already exposes today (see useAnalytics.ts's own docstring for the
 * exact scope boundary: no new aggregation endpoint, no new model,
 * nothing fabricated). Every number on this page traces back to a real
 * row from an endpoint another page already calls.
 *
 * What's deliberately NOT here, and why (see the M8.9 scope discussion):
 * a cross-domain Discovered->Researched->Outreach->Replied->Won
 * conversion funnel (no such tracked chain exists in the backend - see
 * PipelineFunnel.tsx's own identical finding), and CSV export (no export
 * mechanism exists anywhere in this codebase yet). Conversation/reply
 * analytics is no longer missing for the reason this comment used to
 * say - M6.5 (Conversations.tsx) and M6.6 (CRM Automation) both shipped
 * after this page did; a dedicated Conversation/Task analytics view is
 * simply out of this page's own scope (M8.9 predates both), not still
 * blocked on a missing API.
 */

const STATUS_TONE: Record<string, BadgeTone> = {
  completed: "success",
  partially_completed: "warning",
  failed: "danger",
  pending: "neutral",
  running: "info",
  cancelled: "neutral",
};

function formatDuration(ms: number | null): string {
  if (ms == null) return "—";
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  return `${Math.round(minutes / 60)}h`;
}

function JobHealthCard({ title, summary }: { title: string; summary: JobHealthSummary }) {
  const statusEntries = Object.entries(summary.countsByStatus).sort((a, b) => b[1] - a[1]);
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-slate-100">{title}</h3>
        <span className="text-xs text-slate-500">{summary.total} total</span>
      </div>
      {summary.total === 0 ? (
        <PlaceholderNotice kind="no-data" reason={`No ${title.toLowerCase()} jobs have run yet.`} />
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {statusEntries.map(([status, count]) => (
              <Badge key={status} tone={STATUS_TONE[status] ?? "neutral"}>
                {status}: {count}
              </Badge>
            ))}
          </div>
          <p className="text-xs text-slate-500">Average duration: {formatDuration(summary.avgDurationMs)}</p>
        </>
      )}
    </Card>
  );
}

function CountryTable({ rows }: { rows: CountryAggregate[] }) {
  const columns: TableColumn<CountryAggregate>[] = [
    { key: "country", header: "Country", render: (r) => r.country, sortable: true, sortValue: (r) => r.country },
    { key: "count", header: "Prospects", render: (r) => r.count, sortable: true, sortValue: (r) => r.count, align: "right" },
    {
      key: "avgScore",
      header: "Avg. Score",
      render: (r) => (r.avgScore != null ? r.avgScore.toFixed(0) : "—"),
      sortable: true,
      sortValue: (r) => r.avgScore ?? -1,
      align: "right",
    },
  ];
  return <Table columns={columns} rows={rows} rowKey={(r) => r.country} emptyMessage="No prospects with a country recorded yet." />;
}

interface DeliveryCampaignRow {
  id: string;
  name: string;
  status: string;
}

function DeliveryTable({ companyId, campaigns }: { companyId: string; campaigns: DeliveryCampaignRow[] }) {
  const [stats, setStats] = useState<Record<string, CampaignQueueStats | "loading" | "error">>({});

  const loadStats = (campaignId: string) => {
    setStats((prev) => ({ ...prev, [campaignId]: "loading" }));
    fetchCampaignQueueStats(companyId, campaignId)
      .then((result) => setStats((prev) => ({ ...prev, [campaignId]: result })))
      .catch(() => setStats((prev) => ({ ...prev, [campaignId]: "error" })));
  };

  const columns: TableColumn<DeliveryCampaignRow>[] = [
    { key: "name", header: "Campaign", render: (r) => r.name, sortable: true, sortValue: (r) => r.name },
    {
      key: "status",
      header: "Status",
      render: (r) => <Badge tone={STATUS_TONE[r.status] ?? "neutral"}>{r.status}</Badge>,
      sortable: true,
      sortValue: (r) => r.status,
    },
    {
      key: "stats",
      header: "Sent / Failed / Pending",
      render: (r) => {
        const s = stats[r.id];
        if (!s) {
          return (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                loadStats(r.id);
              }}
              className="text-xs font-medium text-slate-300 underline hover:text-white"
            >
              Load stats
            </button>
          );
        }
        if (s === "loading") return <span className="text-xs text-slate-500">Loading…</span>;
        if (s === "error") return <span className="text-xs text-status-danger">Could not load</span>;
        return (
          <span className="text-xs text-slate-300">
            <span className="text-status-success">{s.sent}</span> / <span className="text-status-danger">{s.failed}</span> /{" "}
            <span className="text-slate-400">{s.pending}</span>
          </span>
        );
      },
      align: "right",
    },
  ];

  return <Table columns={columns} rows={campaigns} rowKey={(r) => r.id} emptyMessage="No delivery campaigns yet." />;
}

export default function Analytics() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const navigate = useNavigate();
  const { prospects, isLoading: prospectsLoading } = useDashboardPortfolio();
  const { data, isLoading: analyticsLoading } = useAnalytics();

  if (!companiesLoading && !activeCompanyId) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="max-w-md text-center">
          <h1 className="text-lg font-semibold text-slate-100">Select a business</h1>
          <p className="mt-2 text-sm text-slate-400">Analytics is scoped to one business at a time.</p>
          <button
            onClick={() => navigate("/businesses/new")}
            className="mt-4 rounded-lg bg-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-accent-primary/90"
          >
            Add your business
          </button>
        </Card>
      </div>
    );
  }

  const statusCounts = countByStatus(prospects);
  const maxStatusCount = Math.max(1, ...Object.values(statusCounts));
  const countryRows = aggregateByCountry(prospects);

  const prospectsTab = (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard label="Total Prospects" value={prospects.length} icon={Users} />
        <KpiCard
          label="Average Score"
          value={averageScore(prospects) != null ? averageScore(prospects)!.toFixed(0) : undefined}
          placeholderKind={averageScore(prospects) == null ? "no-data" : undefined}
          icon={Star}
        />
        <KpiCard label="Needs Review" value={countNeedsReview(prospects)} icon={Layers} />
        <KpiCard label="Countries" value={countryRows.length} icon={BarChart3} />
      </div>

      <Card>
        <h3 className="mb-3 font-semibold text-slate-100">Prospect Funnel</h3>
        {prospects.length === 0 ? (
          <PlaceholderNotice kind="no-data" reason="No prospects discovered yet." />
        ) : (
          <div className="space-y-2">
            {PROSPECT_STATUS_ORDER.filter((status) => statusCounts[status]).map((status) => (
              <div key={status} className="flex items-center gap-3 text-sm">
                <span className="w-32 shrink-0 text-slate-400">{PROSPECT_STATUS_LABELS[status] ?? status}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                  <div
                    className="h-full rounded-full bg-accent-primary"
                    style={{ width: `${(statusCounts[status] / maxStatusCount) * 100}%` }}
                  />
                </div>
                <span className="w-10 shrink-0 text-right text-slate-300">{statusCounts[status]}</span>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <h3 className="mb-3 font-semibold text-slate-100">Prospects by Country</h3>
        <CountryTable rows={countryRows} />
      </Card>
    </div>
  );

  const executionTab = (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      <JobHealthCard title="Discovery" summary={data.discovery} />
      <JobHealthCard title="Research" summary={data.research} />
      <JobHealthCard title="Personalization" summary={data.personalization} />
      <JobHealthCard title="Outreach" summary={data.outreach} />
    </div>
  );

  const deliveryTab = (
    <Card>
      <h3 className="mb-3 font-semibold text-slate-100">Delivery Campaigns</h3>
      <DeliveryTable companyId={activeCompanyId ?? ""} campaigns={data.campaigns} />
    </Card>
  );

  return (
    <div>
      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Analytics</h1>
      <p className="mb-6 text-body text-slate-400">
        Real execution and portfolio data across every AI engine - nothing on this page is estimated or simulated.
      </p>

      {(prospectsLoading || analyticsLoading) && <p className="text-sm text-slate-500">Loading…</p>}

      {!prospectsLoading && !analyticsLoading && (
        <Tabs
          items={[
            { id: "prospects", label: "Prospects", content: prospectsTab },
            { id: "execution", label: "AI Workforce Execution", content: executionTab },
            { id: "delivery", label: "Delivery", content: deliveryTab },
          ]}
        />
      )}
    </div>
  );
}
