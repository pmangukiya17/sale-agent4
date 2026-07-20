import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { WorkflowExecutionView } from "../components/WorkflowExecutionView";
import { Button, Card } from "../design-system";
import { useDiscoveryExecution } from "../discovery/useDiscoveryExecution";

interface DiscoverySearchSummary {
  id: string;
  name: string;
  provider_keys: string[];
}

/**
 * DiscoveryExecutionPage — M8.8, Principle 3's exact user flow: Create
 * Search -> Start Discovery -> Live Workflow Progress -> Results. This is
 * the "Live Workflow Progress" screen, reached only after a search has
 * actually been started (see DiscoverySearches.tsx's handleRun, which
 * navigates here right after POST .../run returns "queued"). The existing
 * Discovery configuration page (DiscoverySearches.tsx) itself is
 * unchanged - this is a separate route/page, not a mode of that one.
 *
 * All live state comes from useDiscoveryExecution (the Discovery-specific
 * adapter over the reusable WorkflowExecutionView) - this page owns only
 * the one Discovery-specific fetch needed to know which providers this
 * search enabled (for the dynamic stage list) and the "Results" step's
 * destination link once the run reaches a terminal state.
 */
export default function DiscoveryExecutionPage() {
  const { companyId, searchId } = useParams();
  const [search, setSearch] = useState<DiscoverySearchSummary | null>(null);

  useEffect(() => {
    if (!companyId || !searchId) return;
    apiClient
      .get<DiscoverySearchSummary>(`/company-profiles/${companyId}/discovery-searches/${searchId}`)
      .then((res) => setSearch(res.data))
      .catch(() => setSearch(null));
  }, [companyId, searchId]);

  const { isLoading, error, viewProps } = useDiscoveryExecution(companyId, searchId, search?.provider_keys ?? []);

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Businesses", to: "/businesses" },
          { label: "Discovery", to: `/businesses/${companyId}/discovery/searches` },
          { label: search?.name ?? "Live Progress" },
        ]}
      />

      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Live Workflow Progress</h1>
      <p className="mb-6 text-body text-slate-400">
        Real-time execution of {search ? `"${search.name}"` : "this search"} - updates as the Workflow Engine actually
        runs it, no simulated progress.
      </p>

      {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

      {isLoading && !search ? (
        <Card className="h-40 animate-pulse">{null}</Card>
      ) : (
        <WorkflowExecutionView
          title={search?.name ?? "Discovery search"}
          subtitle="Buyer Discovery"
          resultsAction={
            <Link to={`/businesses/${companyId}/discovery/prospects`}>
              <Button size="sm">View Results</Button>
            </Link>
          }
          {...viewProps}
        />
      )}
    </div>
  );
}
