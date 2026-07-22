import { Link, useParams } from "react-router-dom";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { WorkflowExecutionView } from "../components/WorkflowExecutionView";
import { Button } from "../design-system";
import { useResearchExecution } from "../research/useResearchExecution";

/**
 * ResearchExecutionPage — M8.10, exact structural mirror of
 * DiscoveryExecutionPage.tsx (M8.8): the "Live Workflow Progress" screen
 * for Research, reached only after ProspectResearch.tsx's runRequest
 * navigates here post-POST .../run. That page's own request-creation/
 * document-pasting UI is otherwise unchanged.
 */
export default function ResearchExecutionPage() {
  const { companyId, prospectId, requestId } = useParams();
  const { isLoading, error, viewProps } = useResearchExecution(companyId, requestId);

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Businesses", to: "/businesses" },
          { label: "Prospects", to: `/businesses/${companyId}/discovery/prospects` },
          { label: "Research", to: `/businesses/${companyId}/prospects/${prospectId}/research` },
          { label: "Live Progress" },
        ]}
      />

      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Live Workflow Progress</h1>
      <p className="mb-6 text-body text-slate-400">
        Real-time AI Research execution - updates as the Workflow Engine actually runs it, no simulated progress.
      </p>

      {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

      {!isLoading && (
        <WorkflowExecutionView
          title="Research run"
          subtitle="AI Research"
          resultsAction={
            <Link to={`/businesses/${companyId}/prospects/${prospectId}/research`}>
              <Button size="sm">View Results</Button>
            </Link>
          }
          {...viewProps}
        />
      )}
    </div>
  );
}
