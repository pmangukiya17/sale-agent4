import { Link, useParams } from "react-router-dom";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { WorkflowExecutionView } from "../components/WorkflowExecutionView";
import { Button } from "../design-system";
import { usePersonalizationExecution } from "../personalization/usePersonalizationExecution";

/**
 * PersonalizationExecutionPage — M8.11, exact structural mirror of
 * ResearchExecutionPage.tsx (M8.10) / DiscoveryExecutionPage.tsx (M8.8):
 * the "Live Workflow Progress" screen for Personalization, reached only
 * after ProspectStrategy.tsx's runRequest navigates here post-POST
 * .../run. That page's own request-creation/snapshot-viewing UI is
 * otherwise unchanged.
 */
export default function PersonalizationExecutionPage() {
  const { companyId, prospectId, requestId } = useParams();
  const { isLoading, error, viewProps } = usePersonalizationExecution(companyId, requestId);

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Businesses", to: "/businesses" },
          { label: "Prospects", to: `/businesses/${companyId}/discovery/prospects` },
          { label: "Strategy", to: `/businesses/${companyId}/prospects/${prospectId}/strategy` },
          { label: "Live Progress" },
        ]}
      />

      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Live Workflow Progress</h1>
      <p className="mb-6 text-body text-slate-400">
        Real-time AI Personalization execution - updates as the Workflow Engine actually runs it, no simulated progress.
      </p>

      {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

      {!isLoading && (
        <WorkflowExecutionView
          title="Strategy run"
          subtitle="AI Personalization"
          resultsAction={
            <Link to={`/businesses/${companyId}/prospects/${prospectId}/strategy`}>
              <Button size="sm">View Results</Button>
            </Link>
          }
          {...viewProps}
        />
      )}
    </div>
  );
}
