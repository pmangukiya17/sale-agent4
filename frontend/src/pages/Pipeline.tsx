import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { TransitionalBanner } from "../components/TransitionalBanner";
import { Table, PlaceholderNotice, type TableColumn } from "../design-system";

interface Company {
  id: string;
  name: string;
  country: string | null;
  stage: string;
  icp_score: number | null;
  created_at: string;
}

const COLUMNS: TableColumn<Company>[] = [
  {
    key: "name",
    header: "Company",
    sortable: true,
    sortValue: (c) => c.name,
    render: (c) => <span className="font-medium text-slate-100">{c.name}</span>,
  },
  { key: "country", header: "Country", sortable: true, sortValue: (c) => c.country ?? "", render: (c) => c.country ?? "—" },
  { key: "stage", header: "Stage", sortable: true, sortValue: (c) => c.stage, render: (c) => c.stage },
  {
    key: "icp_score",
    header: "ICP Score",
    sortable: true,
    sortValue: (c) => c.icp_score ?? -1,
    render: (c) => (c.icp_score !== null ? c.icp_score.toFixed(0) : "—"),
  },
];

/**
 * Pipeline — M8.7 Phase E1 (CRM zone). Migrated in place per Design Bible
 * Section 9.2: same data-fetching (a single GET /companies, unchanged),
 * only the presentation layer moves onto the design system (Table,
 * PlaceholderNotice, TransitionalBanner now restyled dark alongside this
 * page) instead of the original light-mode markup. Still the legacy,
 * pre-M1 CRM company list - the banner explains that context; this
 * migration is a restyle only, not a scope change.
 */
export default function Pipeline() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get<Company[]>("/companies")
      .then((res) => setCompanies(res.data))
      .catch(() => setError("Could not load companies."))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <div>
      <TransitionalBanner title="This is the original, pre-M1 CRM company list.">
        It's kept reachable during the M8 rebuild but is no longer the product's primary pipeline view - see the real,
        AI-driven prospect pipeline in the Command Center instead. This page moves or retires once a real
        opportunity/deal-value model exists.
      </TransitionalBanner>

      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Pipeline</h1>
      <p className="mb-6 text-body text-slate-400">
        Companies currently tracked in the CRM. Discovery, scoring, and outreach are not wired up yet — this view
        proves the data path end to end.
      </p>

      {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

      {!isLoading && !error && companies.length === 0 ? (
        <PlaceholderNotice kind="no-data" reason="No companies yet." />
      ) : (
        <Table columns={COLUMNS} rows={companies} rowKey={(c) => c.id} isLoading={isLoading} emptyMessage="No companies yet." />
      )}
    </div>
  );
}
