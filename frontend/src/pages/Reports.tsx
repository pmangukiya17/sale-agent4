import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Badge, Card, PlaceholderNotice, Table } from "../design-system";
import type { BadgeTone, TableColumn } from "../design-system";
import { useCompanies } from "../companies/CompanyContext";
import { useOutreachHistory, type OutreachJob } from "../reports/useOutreachHistory";

/**
 * Reports — M8.9. Per the IA reconciliation table's "Reports: List ->
 * Detail" and the approved minimum-scope decision: this page does NOT
 * re-implement job/run history for Discovery, Research, Personalization,
 * or Delivery - dedicated pages already exist for every one of those
 * (DiscoveryJobs.tsx, ResearchJobs.tsx, PersonalizationJobs.tsx,
 * DeliveryCampaigns.tsx), each already a real List -> Detail view over
 * the exact same backend endpoints. Rebuilding them here would be exactly
 * the duplicate-system problem the Design Debt Budget (Section 10.1) has
 * already ruled out for Badge/StatusBadge and empty-states elsewhere in
 * this codebase - so this page links to them instead.
 *
 * The one genuinely new thing here: Outreach's job/run history
 * (outreach-jobs / outreach-runs) has NO consuming page anywhere in this
 * app today (confirmed by reading ProspectOutreach.tsx - it only touches
 * playbooks/requests/drafts) - that real gap is what this page actually
 * builds, using the same already-existing endpoints and the same
 * List -> Detail expand pattern the other job-history pages use.
 *
 * No CSV/export button anywhere on this page - no export mechanism
 * exists in this backend yet (see the M8.9 scope decision); adding one
 * here would be inventing new backend capability disguised as a frontend
 * feature.
 */

const STATUS_TONE: Record<string, BadgeTone> = {
  completed: "success",
  partially_completed: "warning",
  failed: "danger",
  pending: "neutral",
  running: "info",
  cancelled: "neutral",
};

function OutreachHistoryPanel() {
  const { jobs, runsByJobId, prospectNameById, isLoading, error } = useOutreachHistory();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const columns: TableColumn<OutreachJob>[] = [
    {
      key: "prospect",
      header: "Prospect",
      render: (job) => prospectNameById[job.prospect_id] ?? job.prospect_id,
      sortable: true,
      sortValue: (job) => prospectNameById[job.prospect_id] ?? job.prospect_id,
    },
    {
      key: "status",
      header: "Status",
      render: (job) => <Badge tone={STATUS_TONE[job.status] ?? "neutral"}>{job.status}</Badge>,
      sortable: true,
      sortValue: (job) => job.status,
    },
    {
      key: "started_at",
      header: "Started",
      render: (job) => (job.started_at ? new Date(job.started_at).toLocaleString() : "—"),
      sortable: true,
      sortValue: (job) => job.started_at ?? "",
    },
  ];

  return (
    <Card>
      <h3 className="mb-1 font-semibold text-slate-100">Outreach Runs</h3>
      <p className="mb-3 text-xs text-slate-500">Every AI Outreach draft-generation run, per contact.</p>
      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}
      {!isLoading && jobs.length === 0 ? (
        <PlaceholderNotice kind="no-data" reason="No outreach has been generated yet." />
      ) : (
        <Table
          columns={columns}
          rows={jobs}
          rowKey={(job) => job.id}
          isLoading={isLoading}
          onRowClick={(job) => setExpandedId((prev) => (prev === job.id ? null : job.id))}
        />
      )}
      {expandedId &&
        (() => {
          const job = jobs.find((j) => j.id === expandedId);
          const run = job ? runsByJobId[job.id] : undefined;
          if (!job) return null;
          return (
            <div className="mt-3 space-y-2 border-t border-border-hairline pt-3 text-sm">
              {job.error_message && <p className="text-status-danger">{job.error_message}</p>}
              <p className="text-xs text-slate-500">
                Prospect contact: {job.prospect_contact_id} · Finished:{" "}
                {job.finished_at ? new Date(job.finished_at).toLocaleString() : "—"}
              </p>
              {run && (
                <>
                  <p className="text-xs text-slate-500">
                    Draft version created: {run.outreach_draft_version_created ?? "—"}
                  </p>
                  <div>
                    <p className="mb-1 font-medium text-slate-200">Configuration used</p>
                    <pre className="overflow-x-auto rounded-lg bg-surface-2 p-2 text-xs text-slate-300">
                      {JSON.stringify(run.config_snapshot, null, 2)}
                    </pre>
                  </div>
                </>
              )}
            </div>
          );
        })()}
    </Card>
  );
}

function OtherReportsLinks({ companyId }: { companyId: string }) {
  const links = [
    { label: "Discovery Jobs", to: `/businesses/${companyId}/discovery/jobs` },
    { label: "Research Jobs", to: `/businesses/${companyId}/research/jobs` },
    { label: "Personalization Jobs", to: `/businesses/${companyId}/personalization/jobs` },
    { label: "Delivery Campaigns", to: `/businesses/${companyId}/delivery/campaigns` },
  ];
  return (
    <Card>
      <h3 className="mb-1 font-semibold text-slate-100">Other Reports</h3>
      <p className="mb-3 text-xs text-slate-500">
        Already have their own dedicated List -&gt; Detail history pages - linked here rather than duplicated.
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {links.map((link) => (
          <Link
            key={link.to}
            to={link.to}
            className="rounded-lg border border-border-hairline px-3 py-2 text-sm text-slate-300 hover:border-border-hairline-strong hover:text-slate-100"
          >
            {link.label}
          </Link>
        ))}
      </div>
    </Card>
  );
}

export default function Reports() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const navigate = useNavigate();

  if (!companiesLoading && !activeCompanyId) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="max-w-md text-center">
          <h1 className="text-lg font-semibold text-slate-100">Select a business</h1>
          <p className="mt-2 text-sm text-slate-400">Reports is scoped to one business at a time.</p>
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

  return (
    <div className="space-y-4">
      <div>
        <h1 className="mb-1 text-h1 font-semibold text-slate-100">Reports</h1>
        <p className="text-body text-slate-400">Every AI engine's run history, in one place.</p>
      </div>

      <OutreachHistoryPanel />

      {activeCompanyId && <OtherReportsLinks companyId={activeCompanyId} />}
    </div>
  );
}
